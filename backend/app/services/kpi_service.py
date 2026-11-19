"""Challenge KPIs, recomputed from the baseline and the accepted fixes.

Every factor comes from the data, the catalogue or assumptions.yaml. Ratios whose divisor
is zero are returned as None (shown as "—" in the UI), never as infinity or NaN.
"""

from __future__ import annotations

from app.services.dataset import Dataset
from app.services.effect_service import AppliedFix, PointState


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 1e-9 else None


def _network_state_kpis(ds: Dataset, state: dict[str, PointState]) -> dict[str, float]:
    a = ds.assumptions
    segs = [p for p in ds.points if p.kind == "segment"]
    comfortable_m = sum(p.length_m for p in segs if state[p.id].utci < a["comfortable_utci_c"])
    water_m = sum(p.length_m for p in segs if state[p.id].water_dist_m <= a["water_ok_m"])
    total_m = sum(p.length_m for p in segs)
    return {
        "trail_km": total_m / 1000,
        "comfortable_km": comfortable_m / 1000,
        "water_reachable_km": water_m / 1000,
    }


def recovered_trips(ds: Dataset, base: dict[str, PointState], now: dict[str, PointState]) -> float:
    """Daily trips won back in summer.

    Per trail: share = (length-weighted UTCI drop) / (trail UTCI - cool benchmark UTCI), clamped to 0..1;
    recovered riders = (spring - summer riders) x share. Rider-km on the (synthetic) trail length are
    summed and divided by the average trip length, so one trip is not counted on every trail it crosses.
    """
    a = ds.assumptions
    benchmark = sum(ds.trails[t].utci for t in a["cool_benchmark_trails"]) / len(a["cool_benchmark_trails"])
    rider_km = 0.0
    for trail in ds.trails.values():
        segs = [p for p in ds.points if p.kind == "segment" and p.trail_id == trail.id]
        length = sum(p.length_m for p in segs)
        gap = trail.utci - benchmark
        if length <= 0 or gap <= 0:
            continue
        drop = sum((base[p.id].utci - now[p.id].utci) * p.length_m for p in segs) / length
        share = max(0.0, min(1.0, drop / gap))
        rider_km += (trail.riders_spring - trail.riders_summer) * share * trail.synthetic_length_km
    return rider_km / a["avg_trip_km"]


def compute_kpis(
    ds: Dataset, base: dict[str, PointState], now: dict[str, PointState], plan: list[AppliedFix]
) -> dict:
    a = ds.assumptions
    before = _network_state_kpis(ds, base)
    after = _network_state_kpis(ds, now)

    drops = [base[pid].utci - now[pid].utci for pid in now if base[pid].utci - now[pid].utci > 1e-9]
    trips = recovered_trips(ds, base, now)
    cyclists = trips / a["trips_per_cyclist_day"]
    capex = sum(f.cost_eur for f in plan)
    opex = sum(f.opex_eur_yr for f in plan)
    sequestration_kg = sum(f.co2_kg_yr for f in plan)
    trips_co2_kg = trips * a["co2_per_trip_kg"] * a["summer_days"]
    comfortable_gain = after["comfortable_km"] - before["comfortable_km"]

    return {
        "before": before,
        "after": after,
        "comfortable_km_gain": comfortable_gain,
        "utci_drop_avg_c": sum(drops) / len(drops) if drops else None,
        "utci_drop_max_c": max(drops) if drops else None,
        "points_cooled": len(drops),
        "recovered_trips_per_day": trips,
        "new_summer_cyclists": cyclists,
        "co2_t_per_year": (trips_co2_kg + sequestration_kg) / 1000,
        "co2_from_trips_t": trips_co2_kg / 1000,
        "co2_from_sequestration_t": sequestration_kg / 1000,
        "capex_eur": capex,
        "opex_eur_per_year": opex,
        "eur_per_comfortable_km": _ratio(capex, comfortable_gain),
        "eur_per_new_cyclist": _ratio(capex, cyclists),
        "eur_saved_per_cyclist_year": a["trips_per_cyclist_day"] * a["eur_per_trip"] * a["summer_days"],
        "eur_saved_total_year": trips * a["eur_per_trip"] * a["summer_days"],
    }
