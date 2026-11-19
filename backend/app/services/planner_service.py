"""Stateless planner: every call recomputes from the baseline plus the client's list of accepted fixes."""

from __future__ import annotations

from app.services.dataset import Dataset, MapPoint
from app.services.effect_service import (
    FIX_RULES,
    PlanError,
    PointState,
    apply_fix,
    baseline_state,
    describe_fix,
    effect_summary,
    plan_state,
    validate_plan,
)
from app.services.kpi_service import compute_kpis
from app.services.metric_service import METRICS, priority, score_all, total_priority, wait_exposure

WORST_N = 10


def _check_metric(metric: str) -> None:
    if metric not in METRICS:
        raise PlanError(f"Unknown metric '{metric}'. Use one of {', '.join(METRICS)}.")


def _raw(ds: Dataset, p: MapPoint, s: PointState) -> dict:
    raw = {"utci_c": round(s.utci, 2), "solar": round(s.solar, 1), "water_dist_m": round(s.water_dist_m, 1)}
    if p.kind == "junction":
        raw.update(wait_s=s.wait_s, shade_pct=s.shade_pct, wait_exposure=round(wait_exposure(ds, s), 4))
    return raw


def static_map_data(ds: Dataset) -> dict:
    a = ds.assumptions
    return {
        "trails": [t.raw for t in ds.trails.values()],
        "points": [
            {k: v for k, v in p.raw.items() if k not in ("utm", "mid_utm")} | {"riders_spring": ds.trails[p.trail_id].riders_spring}
            for p in ds.points
        ],
        "fountains": [{"id": f["id"], "location": f["location"], "wgs": f["wgs"]} for f in ds.fountains],
        "context_network": ds.context_network,
        "catalogue": [
            {
                **ds.catalogue[fid],
                "label": rule["label"],
                "allowed_on": sorted(rule["kinds"]),
                "priced_per_m": rule["linear"],
                "effects": effect_summary(ds, fid),
            }
            for fid, rule in FIX_RULES.items()
        ],
        "assumptions": ds.assumption_list,
        "solar_range": [ds.solar_min, ds.solar_max],
        "metrics": [
            {
                "id": "water",
                "label": "Water access",
                "description": f"Distance to drinking water: fine within {a['water_ok_m']} m, worst from {a['water_bad_m']} m.",
            },
            {
                "id": "sun",
                "label": "Sun exposure",
                "description": "Real solar exposure of the street; at junctions also the red-light wait in full sun.",
            },
            {
                "id": "heat",
                "label": "Heat stress",
                "description": f"UTCI felt temperature at 14:00: fine at {a['utci_ok_c']} °C, worst at {a['utci_bad_c']} °C.",
            },
            {"id": "combined", "label": "Combined", "description": "Equal-weight mean of water, sun and heat."},
        ],
    }


def evaluate(ds: Dataset, metric: str, budget: float, accepted: list[tuple[str, str]]) -> dict:
    _check_metric(metric)
    plan = validate_plan(ds, accepted, budget)
    base = baseline_state(ds)
    state = plan_state(ds, accepted)
    base_scores = score_all(ds, base)
    scores = score_all(ds, state)

    rows = []
    for p in ds.points:
        sc = scores[p.id]
        rows.append(
            {
                "id": p.id,
                "scores": {k: round(v, 4) for k, v in sc.as_dict().items()},
                "raw": _raw(ds, p, state[p.id]),
                "priority": round(priority(ds, p, sc.get(metric)), 3),
            }
        )
    worst = sorted((r for r in rows if r["priority"] > 0), key=lambda r: (-r["priority"], r["id"]))[:WORST_N]
    spent = sum(f.cost_eur for f in plan)
    burden_before = total_priority(ds, base_scores, metric)
    burden_now = total_priority(ds, scores, metric)
    return {
        "metric": metric,
        "points": rows,
        "worst": [r["id"] for r in worst],
        "budget": {"total": budget, "spent": round(spent, 2), "remaining": round(budget - spent, 2)},
        "plan": [
            {
                "fix_id": f.fix_id,
                "point_id": f.point_id,
                "label": FIX_RULES[f.fix_id]["label"],
                "cost_eur": f.cost_eur,
                "opex_eur_yr": f.opex_eur_yr,
            }
            for f in plan
        ],
        "oases": [
            {"point_id": pid, "wgs": ds.points_by_id[pid].raw["mid_wgs"]} for fid, pid in accepted if fid == "INT-03"
        ],
        "burden": {
            "baseline": burden_before,
            "current": burden_now,
            "reduction_pct": (1 - burden_now / burden_before) * 100 if burden_before > 0 else None,
        },
        "kpis": compute_kpis(ds, base, state, plan),
    }


def recommend(ds: Dataset, metric: str, budget: float, accepted: list[tuple[str, str]], point_id: str) -> dict:
    _check_metric(metric)
    plan = validate_plan(ds, accepted, budget)
    point = ds.points_by_id.get(point_id)
    if point is None:
        raise PlanError(f"Unknown point '{point_id}'.")
    remaining = budget - sum(f.cost_eur for f in plan)
    state = plan_state(ds, accepted)
    scores = score_all(ds, state)
    burden = total_priority(ds, scores, metric)
    local_before = scores[point_id].get(metric)
    applied_here = {fid for fid, pid in accepted if pid == point_id}

    options = []
    for fix_id, rule in FIX_RULES.items():
        if point.kind not in rule["kinds"]:
            continue
        priced = describe_fix(ds, fix_id, point)
        if fix_id in applied_here:
            options.append(
                {"fix_id": fix_id, "label": rule["label"], "status": "applied", "cost_eur": priced.cost_eur,
                 "effects": effect_summary(ds, fix_id)}
            )
            continue
        new_scores = score_all(ds, apply_fix(ds, state, fix_id, point))
        new_burden = total_priority(ds, new_scores, metric)
        reduction = burden - new_burden
        improves = reduction > 1e-6
        affordable = priced.cost_eur <= remaining + 0.005
        reduction_pct = reduction / burden * 100 if burden > 0 else 0.0
        options.append(
            {
                "fix_id": fix_id,
                "label": rule["label"],
                "description": ds.catalogue[fix_id]["description"],
                "status": "available" if improves and affordable else ("over_budget" if improves else "no_effect"),
                "cost_eur": priced.cost_eur,
                "opex_eur_yr": priced.opex_eur_yr,
                "deployment_weeks": ds.catalogue[fix_id]["deployment_weeks"],
                "effects": effect_summary(ds, fix_id),
                "local_before": round(local_before, 4),
                "local_after": round(new_scores[point_id].get(metric), 4),
                "network_reduction_pct": reduction_pct,
                "value_pct_per_10k": reduction_pct / priced.cost_eur * 10_000 if priced.cost_eur > 0 else None,
            }
        )
    status_order = {"available": 0, "over_budget": 1, "no_effect": 2, "applied": 3}
    options.sort(key=lambda o: (status_order[o["status"]], -(o.get("value_pct_per_10k") or 0.0)))
    return {
        "point_id": point_id,
        "metric": metric,
        "remaining_eur": round(remaining, 2),
        "local_score": round(local_before, 4),
        "options": options,
    }
