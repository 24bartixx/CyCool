"""Challenge KPIs (VAS-R1), recomputed from the baseline and the accepted fixes.

Every factor comes from the data, the catalogue (INT-08 for replaced trips) or assumptions.yaml.
Ratios whose divisor is zero are returned as None (shown as "—" in the UI), never as infinity or NaN.
"""

from __future__ import annotations

from app.services.dataset import Dataset, clamp01
from app.services.effect_service import FIX_RULES, AppliedFix, PointState, targets
from app.services.metric_service import exposure_s, riders

EPS = 1e-9
PV_FIXES = ("INT-06",)  # CO2 avoided by solar power, not captured by plants


def fix_lifetimes(a: dict) -> dict[str, float]:
    """{fix id: service life in years}, from entries like "INT-01 → 30"."""
    out = {}
    for entry in a["fix_lifetime_yr"]:
        fix_id, years = (part.strip() for part in entry.split("→"))
        out[fix_id] = float(years)
    return out


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > EPS else None


def _scenario_utci(ds: Dataset, state: dict[str, PointState], scenario: str, point_id: str) -> float:
    """UTCI of a point in a KPI weather scenario: that scenario's baseline minus the plan's UTCI cut here."""
    s = state[point_id]
    return ds.scenario_utci[scenario][point_id] - (s.utci_base - s.utci)


def _network_state_kpis(ds: Dataset, state: dict[str, PointState]) -> dict[str, float]:
    """Km of the whole built network (every piece, on or off the trails).

    Comfortable km are judged on a typical summer afternoon and very strong heat on a heatwave afternoon,
    each with its standard UTCI threshold, so neither reads 0% or 100% today by construction.
    """
    a = ds.assumptions
    segs = [p for p in ds.points if p.kind == "segment"]
    comfortable_m = sum(
        p.length_m for p in segs if _scenario_utci(ds, state, "typical", p.id) < a["comfortable_utci_c"]
    )
    below_strong_heat_m = sum(
        p.length_m for p in segs if _scenario_utci(ds, state, "heatwave", p.id) < a["strong_heat_utci_c"]
    )
    water_m = sum(p.length_m for p in segs if state[p.id].water_dist_m <= a["water_ok_m"])
    total_m = sum(p.length_m for p in segs)
    return {
        "network_km": total_m / 1000,
        "comfortable_km": comfortable_m / 1000,
        "below_strong_heat_km": below_strong_heat_m / 1000,
        "water_reachable_km": water_m / 1000,
    }


def _heat_dose(ds: Dataset, state: dict[str, PointState], trail_id: str, bench_utci: float) -> float:
    """Rider-seconds x UTCI above the comfortable threshold, over the trail's pieces, junctions and stations."""
    return sum(
        riders(ds, p) * exposure_s(ds, p, state[p.id]) * max(0.0, state[p.id].utci - bench_utci)
        for p in ds.points
        if p.trail_id == trail_id
    )


def _recovered_riders(ds: Dataset, base: dict[str, PointState], now: dict[str, PointState]) -> dict[str, float]:
    """Summer riders won back per trail.

    share closed = 1 - heat dose now / heat dose today, where the dose is rider-seconds x UTCI above the
    comfortable threshold, on the trail's pieces, junctions and stations (so shade at a red light, a shorter
    wait and a station canopy count too, weighted by the time people spend there). Clamped to 0..1;
    recovered = (spring - summer riders) x share closed. Pieces off the trails have no synthetic summer
    drop, so they win back no riders.
    """
    bench_utci = float(ds.assumptions["comfortable_utci_c"])
    out = {}
    for tid, trail in ds.trails.items():
        before = _heat_dose(ds, base, tid, bench_utci)
        after = _heat_dose(ds, now, tid, bench_utci)
        share = clamp01(1 - after / before) if before > EPS else 0.0
        out[tid] = max(0.0, trail.riders_spring - trail.riders_summer) * share
    return out


def compute_kpis(
    ds: Dataset, base: dict[str, PointState], now: dict[str, PointState], plan: list[AppliedFix]
) -> dict:
    a = ds.assumptions
    before = _network_state_kpis(ds, base)
    after = _network_state_kpis(ds, now)

    # UTCI drop on pieces (length-weighted) and at critical points.
    cooled_trail_m = 0.0
    weighted_trail_drop = 0.0
    critical_drops: list[float] = []
    critical_total = 0
    for point in ds.points:
        drop = base[point.id].utci - now[point.id].utci
        critical = point.id in ds.critical_ids
        critical_total += critical
        if drop <= EPS:
            continue
        if critical:
            critical_drops.append(drop)
        if point.kind == "segment":
            cooled_trail_m += point.length_m
            weighted_trail_drop += drop * point.length_m

    # Riders won back -> trips -> new summer cyclists; only trips that replace a car save CO2 and money.
    recovered = _recovered_riders(ds, base, now)
    # A won-back rider rides the trail, but at most one average trip, so long trails don't inflate trips.
    trip_km = float(a["avg_trip_km"])
    rider_km = sum(r * min(ds.trails[t].synthetic_length_km, trip_km) for t, r in recovered.items())
    trips_per_day = rider_km / trip_km
    new_cyclists = trips_per_day / float(a["trips_per_cyclist_day"])
    car_share = float(a["car_trip_share"])
    co2_trips_t = trips_per_day * car_share * float(ds.modal_shift["co2_kg_yr"]) * float(a["summer_days"]) / 1000
    eur_saved_car_switcher = float(a["trips_per_cyclist_day"]) * float(a["eur_per_trip"]) * float(a["summer_days"])
    eur_saved_per_cyclist = car_share * eur_saved_car_switcher

    capex = sum(f.cost_eur for f in plan)
    opex = sum(f.opex_eur_yr for f in plan)
    lifetimes = fix_lifetimes(a)
    annual_cost = sum(f.cost_eur / lifetimes[f.fix_id] for f in plan) + opex
    sequestration_t = sum(f.co2_kg_yr for f in plan if f.fix_id not in PV_FIXES) / 1000
    pv_avoided_t = sum(f.co2_kg_yr for f in plan if f.fix_id in PV_FIXES) / 1000
    comfortable_gain = after["comfortable_km"] - before["comfortable_km"]

    # km adapted: pieces under trees or cool pavement that are cooled by at least the adapted threshold.
    # Every tree and cool-pavement euro counts in the cost, also on pieces that stay below the threshold.
    min_drop = float(a["adapted_min_utci_drop_c"])
    linear = [f for f in plan if FIX_RULES[f.fix_id]["linear"]]
    adapted = {
        p.id for f in linear for p in _fixed_pieces(ds, f) if base[p.id].utci - now[p.id].utci >= min_drop - EPS
    }
    adapted_km = sum(ds.points_by_id[pid].length_m for pid in adapted) / 1000
    linear_capex = sum(f.cost_eur for f in linear)

    return {
        "before": before,
        "after": after,
        "comfortable_km_gain": comfortable_gain,
        "utci_drop_trail_avg_c": _ratio(weighted_trail_drop, cooled_trail_m),
        "utci_cooled_trail_km": cooled_trail_m / 1000,
        # Over ALL critical points (uncooled ones count 0), so cooling a few doesn't read as cooling all.
        "critical_drop_avg_c": sum(critical_drops) / critical_total if critical_drops and critical_total else None,
        "critical_drop_cooled_avg_c": sum(critical_drops) / len(critical_drops) if critical_drops else None,
        "critical_drop_max_c": max(critical_drops) if critical_drops else None,
        "critical_cooled": len(critical_drops),
        "critical_total": critical_total,
        "recovered_riders_per_day": sum(recovered.values()),
        "recovered_trips_per_day": trips_per_day,
        "new_summer_cyclists": new_cyclists,
        "co2_t_per_year": co2_trips_t + sequestration_t + pv_avoided_t,
        "co2_trips_t_per_year": co2_trips_t,
        "co2_sequestration_t_per_year": sequestration_t,
        "co2_pv_avoided_t_per_year": pv_avoided_t,
        "capex_eur": capex,
        "opex_eur_per_year": opex,
        "adapted_km": adapted_km,
        "adapted_capex_eur": linear_capex,
        "eur_per_adapted_km": _ratio(linear_capex, adapted_km),
        "eur_per_comfortable_km": _ratio(capex, comfortable_gain),
        "eur_per_new_cyclist": _ratio(capex, new_cyclists),
        "opex_eur_per_new_cyclist_year": _ratio(opex, new_cyclists),
        # Investment spread over each fix's service life, plus upkeep, per new summer cyclist.
        "annual_cost_eur": annual_cost,
        "eur_per_new_cyclist_year": _ratio(annual_cost, new_cyclists),
        "eur_saved_per_cyclist_year": eur_saved_per_cyclist,
        "eur_saved_car_switcher_year": eur_saved_car_switcher,
        "eur_saved_total_year": new_cyclists * eur_saved_per_cyclist,
    }


def _fixed_pieces(ds: Dataset, fix: AppliedFix):
    point = ds.points_by_id[fix.point_id]
    return [p for p in targets(ds, fix.fix_id, point) if p.kind == "segment"]
