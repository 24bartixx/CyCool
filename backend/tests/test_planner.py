import math

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.dataset import get_dataset
from app.services.effect_service import PlanError, baseline_state, plan_state, validate_plan
from app.services.metric_service import score_point
from app.services.planner_service import evaluate, recommend

ds = get_dataset()
A = ds.assumptions
client = TestClient(app)


def first(kind: str):
    return next(p for p in ds.points if p.kind == kind)


def test_dataset_shape():
    assert len(ds.trails) == 13 and "TRM-13" not in ds.trails
    assert len(ds.fountains) == 116
    assert {p.kind for p in ds.points} == {"segment", "junction", "station"}
    assert all(p.length_m <= 100 for p in ds.points if p.kind == "segment")
    assert all(any(p.trail_id == t for p in ds.points) for t in ds.trails)


@pytest.mark.parametrize(
    "dist, expected", [(A["water_ok_m"], 0.0), (A["water_bad_m"], 1.0), ((A["water_ok_m"] + A["water_bad_m"]) / 2, 0.5)]
)
def test_water_score_edges(dist, expected):
    p = first("segment")
    s = baseline_state(ds)[p.id]
    from dataclasses import replace

    assert math.isclose(score_point(ds, p, replace(s, water_dist_m=dist)).water, expected)


@pytest.mark.parametrize("utci, expected", [(A["utci_ok_c"], 0.0), (A["utci_bad_c"], 1.0), (60, 1.0), (10, 0.0)])
def test_heat_score_edges(utci, expected):
    from dataclasses import replace

    p = first("segment")
    s = baseline_state(ds)[p.id]
    assert math.isclose(score_point(ds, p, replace(s, utci=utci)).heat, expected)


def test_oasis_brings_water_within_reach():
    target = max((p for p in ds.points if p.kind == "segment"), key=lambda p: p.fountain_dist_m)
    state = plan_state(ds, [("INT-03", target.id)])
    for p in ds.points:
        if p.geom.distance(target.mid) <= A["water_ok_m"]:
            assert score_point(ds, p, state[p.id]).water == 0.0
    assert state[target.id].water_dist_m < 0.01  # oasis sits on the point (coords rounded to cm)


def test_trees_halve_solar_and_cool():
    p = first("segment")
    base = baseline_state(ds)[p.id]
    after = plan_state(ds, [("INT-01", p.id)])[p.id]
    assert math.isclose(after.solar, base.solar * (1 - A["trees_solar_cut"]))
    assert math.isclose(after.utci, base.utci + ds.catalogue["INT-01"]["utci_reduction_c"])


def test_linear_fix_is_priced_pro_rata():
    p = first("segment")
    plan = validate_plan(ds, [("INT-04", p.id)], 1e9)
    assert math.isclose(plan[0].cost_eur, round(ds.catalogue["INT-04"]["capex_eur"] * p.length_m / 100, 2))


def test_invalid_plans_are_rejected():
    seg, junction = first("segment"), first("junction")
    with pytest.raises(PlanError):
        validate_plan(ds, [("INT-02", seg.id)], 1e9)  # sail only at junctions
    with pytest.raises(PlanError):
        validate_plan(ds, [("INT-05", junction.id), ("INT-05", junction.id)], 1e9)  # duplicate
    with pytest.raises(PlanError):
        validate_plan(ds, [("INT-03", seg.id)], 1000)  # over budget
    with pytest.raises(PlanError):
        validate_plan(ds, [("INT-99", seg.id)], 1e9)
    with pytest.raises(PlanError):
        validate_plan(ds, [("INT-03", "nope")], 1e9)


def test_undo_restores_previous_result_exactly():
    r0 = evaluate(ds, "combined", 100_000, [])
    worst = r0["worst"][0]
    rec = recommend(ds, "combined", 100_000, [], worst)
    best = next(o for o in rec["options"] if o["status"] == "available")
    r1 = evaluate(ds, "combined", 100_000, [(best["fix_id"], worst)])
    assert r1["burden"]["current"] < r0["burden"]["current"]
    r_undo = evaluate(ds, "combined", 100_000, [])
    assert r_undo == r0


@pytest.mark.parametrize("metric", ["water", "sun", "heat", "combined"])
def test_greedy_loop_never_increases_burden_or_overspends(metric):
    budget = 60_000
    accepted: list[tuple[str, str]] = []
    result = evaluate(ds, metric, budget, accepted)
    for _ in range(8):
        picked = None
        for pid in result["worst"]:
            rec = recommend(ds, metric, budget, accepted, pid)
            picked = next((o for o in rec["options"] if o["status"] == "available"), None)
            if picked:
                accepted.append((picked["fix_id"], pid))
                break
        if not picked:
            break
        new = evaluate(ds, metric, budget, accepted)
        assert new["burden"]["current"] < result["burden"]["current"]
        assert new["budget"]["remaining"] >= -0.01
        result = new


def test_kpis_without_plan_have_no_ratios():
    k = evaluate(ds, "heat", 50_000, [])["kpis"]
    assert k["eur_per_comfortable_km"] is None and k["eur_per_new_cyclist"] is None
    assert k["utci_drop_avg_c"] is None and k["capex_eur"] == 0


def test_cooling_a_hot_trail_recovers_riders_and_comfort():
    trail = "TRM-05"  # UTCI 37.2 °C, minus trees 4.5 and cool pavement 1.8 = 30.9 < 32
    segs = [p.id for p in ds.points if p.kind == "segment" and p.trail_id == trail]
    accepted = [("INT-01", s) for s in segs] + [("INT-04", s) for s in segs]
    k = evaluate(ds, "heat", 1e7, accepted)["kpis"]
    real_km = ds.trails[trail].raw["real_length_m"] / 1000
    assert math.isclose(k["comfortable_km_gain"], real_km, abs_tol=1e-3)  # real_length_m is rounded to 0.1 m
    assert k["recovered_trips_per_day"] > 0 and k["eur_per_new_cyclist"] is not None


def test_api_endpoints():
    assert client.get("/api/map-data").status_code == 200
    ok = client.post("/api/evaluate", json={"metric": "water", "budget": 50000, "accepted": []})
    assert ok.status_code == 200 and len(ok.json()["worst"]) == 10
    bad = client.post(
        "/api/evaluate", json={"metric": "water", "budget": 100, "accepted": [{"fix_id": "INT-03", "point_id": ok.json()["worst"][0]}]}
    )
    assert bad.status_code == 422 and "budget" in bad.json()["detail"]
    assert client.post("/api/evaluate", json={"metric": "wind", "budget": 1}).status_code == 422
