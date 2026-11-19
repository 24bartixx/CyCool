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
    below_strong_heat_m = sum(p.length_m for p in segs if state[p.id].utci < a["strong_heat_utci_c"])
    water_m = sum(p.length_m for p in segs if state[p.id].water_dist_m <= a["water_ok_m"])
    total_m = sum(p.length_m for p in segs)
    return {
        "trail_km": total_m / 1000,
        "comfortable_km": comfortable_m / 1000,
        "below_strong_heat_km": below_strong_heat_m / 1000,
        "water_reachable_km": water_m / 1000,
    }


def compute_kpis(
    ds: Dataset, base: dict[str, PointState], now: dict[str, PointState], plan: list[AppliedFix]
) -> dict:
    before = _network_state_kpis(ds, base)
    after = _network_state_kpis(ds, now)

    drops = []
    cooled_trail_m = 0.0
    weighted_trail_drop = 0.0
    for point in ds.points:
        drop = base[point.id].utci - now[point.id].utci
        if drop <= 1e-9:
            continue
        drops.append(drop)
        if point.kind == "segment":
            cooled_trail_m += point.length_m
            weighted_trail_drop += drop * point.length_m

    capex = sum(f.cost_eur for f in plan)
    opex = sum(f.opex_eur_yr for f in plan)
    sequestration_kg = sum(f.co2_kg_yr for f in plan)
    comfortable_gain = after["comfortable_km"] - before["comfortable_km"]

    return {
        "before": before,
        "after": after,
        "comfortable_km_gain": comfortable_gain,
        "utci_drop_avg_c": sum(drops) / len(drops) if drops else None,
        "utci_drop_max_c": max(drops) if drops else None,
        "points_cooled": len(drops),
        "utci_drop_trail_avg_c": _ratio(weighted_trail_drop, cooled_trail_m),
        "utci_cooled_trail_km": cooled_trail_m / 1000,
        "co2_t_per_year": sequestration_kg / 1000,
        "capex_eur": capex,
        "opex_eur_per_year": opex,
        "eur_per_comfortable_km": _ratio(capex, comfortable_gain),
    }
