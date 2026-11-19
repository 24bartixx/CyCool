"""Stateless planner: every call recomputes from the baseline plus the client's list of accepted fixes."""

from __future__ import annotations

import heapq

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
    target_key,
    validate_plan,
)
from app.services.kpi_service import compute_kpis
from app.services.metric_service import (
    METRICS,
    Scores,
    burden,
    score_all,
    score_point,
    severity,
    total_burden,
    unshaded_share,
)

WORST_N = 10


def _check_metric(metric: str) -> None:
    if metric not in METRICS:
        raise PlanError(f"Unknown metric '{metric}'. Use one of {', '.join(METRICS)}.")


def _raw(ds: Dataset, p: MapPoint, s: PointState) -> dict:
    raw = {
        "utci_c": round(s.utci, 2),
        "utci_base_c": round(s.utci_base, 2),
        "solar": round(s.solar, 1),
        "water_dist_m": round(s.water_dist_m, 1),
    }
    if p.kind == "junction":
        raw.update(wait_s=s.wait_s, shade_pct=s.shade_pct)
    return raw


def _local_impacts(ds: Dataset, current: PointState, proposed: PointState, before: Scores, after: Scores) -> list[dict]:
    measurements = {
        "water": (current.water_dist_m, proposed.water_dist_m, "m"),
        "sun": (current.solar, proposed.solar, ""),
        "heat": (current.utci, proposed.utci, "°C"),
    }
    if round(current.solar, 1) == round(proposed.solar, 1):
        measurements["sun"] = (100 * unshaded_share(current), 100 * unshaded_share(proposed), "%")

    impacts = []
    for metric in METRICS:
        before_score, after_score = round(before.get(metric), 4), round(after.get(metric), 4)
        impact: dict[str, object] = {"metric": metric, "before": before_score, "after": after_score}
        if metric in measurements:
            before_value, after_value, unit = measurements[metric]
            before_value, after_value = round(before_value, 1), round(after_value, 1)
            if before_value != after_value:
                impact["measurement"] = {"before": before_value, "after": after_value, "unit": unit}
        if before_score != after_score or "measurement" in impact:
            impacts.append(impact)
    return impacts


def static_map_data(ds: Dataset) -> dict:
    a = ds.assumptions
    return {
        "trails": [t.raw for t in ds.trails.values()],
        "points": [{k: v for k, v in p.raw.items() if k not in ("utm", "mid_utm")} for p in ds.points],
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
                "description": "Real solar index of the street (municipal raster, no stated unit), relative to the whole cycle network; at junctions also the shade of the waiting box (the wait itself is the time spent there).",
            },
            {
                "id": "heat",
                "label": "Heat stress",
                "description": f"UTCI felt temperature at {a['heat_reference_hour']}:00 (synthetic per trail, shifted by real local sun): fine at {a['utci_ok_c']} °C, worst at {a['utci_bad_c']} °C.",
            },
            {
                "id": "combined",
                "label": "Combined",
                "description": (
                    f"Weighted mean: heat {a['weight_heat']}, sun {a['weight_sun']}, water {a['weight_water']} "
                    "(heat already includes local sun, so sun is not weighted equally)."
                ),
            },
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
                "priority": round(severity(ds, p, sc.get(metric)), 3),
                "burden": round(burden(ds, p, state[p.id], sc.get(metric)), 4),
            }
        )
    worst = sorted((r for r in rows if r["priority"] > 0), key=lambda r: (-r["priority"], r["id"]))[:WORST_N]
    spent = sum(f.cost_eur for f in plan)
    burden_before = total_burden(ds, base, base_scores, metric)
    burden_now = total_burden(ds, state, scores, metric)
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
                "length_m": f.length_m,
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
    burden_now = total_burden(ds, state, scores, metric)
    local_before = scores[point_id].get(metric)
    # A linear fix covers the whole street segment, so trees accepted on another piece of it count here too.
    applied_here = {
        fid for fid, pid in accepted
        if fid in FIX_RULES and target_key(ds, fid, ds.points_by_id[pid]) == target_key(ds, fid, point)
    }

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
        new_state = apply_fix(ds, state, fix_id, point)
        new_scores = score_all(ds, new_state)
        new_burden = total_burden(ds, new_state, new_scores, metric)
        reduction = burden_now - new_burden
        improves = reduction > 1e-6
        affordable = priced.cost_eur <= remaining + 0.005
        reduction_pct = reduction / burden_now * 100 if burden_now > 0 else 0.0
        options.append(
            {
                "fix_id": fix_id,
                "label": rule["label"],
                "description": ds.catalogue[fix_id]["description"],
                "status": "available" if improves and affordable else ("over_budget" if improves else "no_effect"),
                "cost_eur": priced.cost_eur,
                "length_m": priced.length_m,
                "opex_eur_yr": priced.opex_eur_yr,
                "deployment_weeks": ds.catalogue[fix_id]["deployment_weeks"],
                "effects": effect_summary(ds, fix_id),
                "local_before": round(local_before, 4),
                "local_after": round(new_scores[point_id].get(metric), 4),
                "local_impacts": _local_impacts(ds, state[point_id], new_state[point_id], scores[point_id], new_scores[point_id]),
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


AUTO_PLAN_MAX_STEPS = 200


def auto_plan(ds: Dataset, metric: str, budget: float, accepted: list[tuple[str, str]]) -> dict:
    """Fills the remaining budget greedily by burden reduction per euro (lazy greedy / CELF).

    Candidates are every allowed (fix, place) not yet in the plan; a linear fix is one candidate per real
    street segment. Each round takes the affordable candidate with the highest reduction per euro of the
    selected metric's burden. Gains only shrink as the plan grows (cooling stacks with a discount, water
    distance can only drop, a shorter wait leaves less to shade), so a stale gain is an upper bound and is
    recomputed only when it reaches the top of the queue. Ranking by gain per euro alone can miss a single
    large fix, so the result is compared with the best single affordable fix and the better one is
    returned (the standard safeguard for a greedy under a budget). It is a heuristic, not a proven optimum.
    """
    _check_metric(metric)
    plan = validate_plan(ds, accepted, budget)
    remaining = budget - sum(f.cost_eur for f in plan)
    state = plan_state(ds, accepted)
    scores = score_all(ds, state)
    taken = {(fid, target_key(ds, fid, ds.points_by_id[pid])) for fid, pid in accepted}

    candidates: dict[tuple[str, str], tuple[str, str, float]] = {}
    for p in ds.points:
        for fix_id, rule in FIX_RULES.items():
            if p.kind not in rule["kinds"]:
                continue
            key = (fix_id, target_key(ds, fix_id, p))
            if key in taken or key in candidates:
                continue
            candidates[key] = (fix_id, p.id, describe_fix(ds, fix_id, p).cost_eur)

    def gain(fix_id: str, point_id: str) -> tuple[float, dict]:
        new_state = apply_fix(ds, state, fix_id, ds.points_by_id[point_id])
        delta = 0.0
        for q in ds.points:
            if new_state[q.id] is not state[q.id]:
                before = burden(ds, q, state[q.id], scores[q.id].get(metric))
                after = burden(ds, q, new_state[q.id], score_point(ds, q, new_state[q.id]).get(metric))
                delta += before - after
        return delta, new_state

    heap: list[tuple[float, int, tuple[str, str]]] = []
    best_single: tuple[float, str, str] | None = None  # (gain, fix_id, point_id) of the best lone fix
    for i, (key, (fix_id, point_id, cost)) in enumerate(candidates.items()):
        if cost <= remaining + 0.005 and cost > 0:
            g, _ = gain(fix_id, point_id)
            if g > 1e-9:
                heapq.heappush(heap, (-g / cost, i, key))
                if best_single is None or g > best_single[0]:
                    best_single = (g, fix_id, point_id)

    added: list[dict] = []
    greedy_gain = 0.0
    fresh_round = 0  # candidates whose gain was computed against the current plan carry this stamp
    stamps: dict[tuple[str, str], int] = {key: 0 for _, _, key in heap}
    while heap and len(added) < AUTO_PLAN_MAX_STEPS:
        neg_ratio, i, key = heapq.heappop(heap)
        fix_id, point_id, cost = candidates[key]
        if cost > remaining + 0.005:
            continue  # no longer affordable; costs don't change, so it never will be again
        if stamps[key] != fresh_round:
            g, _ = gain(fix_id, point_id)
            stamps[key] = fresh_round
            if g > 1e-9:
                heapq.heappush(heap, (-g / cost, i, key))
            continue
        # Fresh and on top: accept it.
        g, state = gain(fix_id, point_id)
        scores = score_all(ds, state)
        remaining -= cost
        greedy_gain += g
        added.append({"fix_id": fix_id, "point_id": point_id})
        fresh_round += 1

    if best_single is not None and best_single[0] > greedy_gain + 1e-9:
        added = [{"fix_id": best_single[1], "point_id": best_single[2]}]

    return {"added": added, "accepted": [{"fix_id": f, "point_id": p} for f, p in accepted] + added}
