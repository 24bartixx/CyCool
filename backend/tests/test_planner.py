import math

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import shape

from app.main import app
from app.services.dataset import get_dataset
from app.services.effect_service import PlanError, baseline_state, plan_state, validate_plan
from app.services.metric_service import burden, exposure_s, score_point
from app.services.planner_service import auto_plan, evaluate, recommend

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


def test_context_layers():
    """Parks (OSM outlines) and Bicibox parkings are display-only layers inside the planner's area."""
    lats = [ll[0] for p in ds.points for ll in p.raw["wgs"]]
    lons = [ll[1] for p in ds.points for ll in p.raw["wgs"]]
    pad = 0.02  # about 2 km around the trails and stations

    def inside(lat: float, lon: float) -> bool:
        return min(lats) - pad <= lat <= max(lats) + pad and min(lons) - pad <= lon <= max(lons) + pad

    assert len(ds.bike_parkings) == 10
    assert all(b["name"] and inside(*b["wgs"]) for b in ds.bike_parkings)
    parks = ds.parks["features"]
    assert parks and all(f["geometry"]["type"] in ("Polygon", "MultiPolygon") for f in parks)
    assert all(f["properties"]["area_m2"] > 0 for f in parks)
    assert all(inside(c.y, c.x) for c in (shape(f["geometry"]).representative_point() for f in parks))
    body = client.get("/api/map-data").json()
    assert len(body["parks"]["features"]) == len(parks) and len(body["bike_parkings"]) == 10


def test_surface_temperature_layer():
    """Landsat LST covers trails and the rest of the network, in a plausible summer range, and is display only."""
    feats = ds.surface_temp["features"]
    on_trail = [f for f in feats if f["properties"]["on_trail"]]
    assert on_trail and len(on_trail) < len(feats)
    assert all(25 <= f["properties"]["lst_c"] <= 65 for f in feats)
    body = client.get("/api/map-data").json()
    assert len(body["surface_temp"]["features"]) == len(feats)


def test_all_real_ambici_stations_are_points():
    stations = [p for p in ds.points if p.kind == "station"]
    assert len(stations) == 17
    assert all(p.id.startswith("AMB-") and p.raw["trail_id"] in ds.trails for p in stations)
    base = baseline_state(ds)
    vas = {p.raw["vas_id"]: p for p in stations if "vas_id" in p.raw}
    assert {k: v.id for k, v in vas.items()} == {"EST-B01": "AMB-34863", "EST-B02": "AMB-34868"}
    for p in vas.values():  # the matched stations add their synthetic temperature anomaly
        assert p.temp_anomaly_c > 0
        assert math.isclose(base[p.id].utci, ds.trails[p.trail_id].utci + p.temp_anomaly_c)
    plain = next(p for p in stations if "vas_id" not in p.raw)
    assert math.isclose(base[plain.id].utci, ds.trails[plain.trail_id].utci)
    validate_plan(ds, [("INT-06", p.id) for p in stations], 1e9)  # a canopy fits every station


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
    assert k["eur_per_comfortable_km"] is None
    assert k["critical_drop_avg_c"] is None and k["capex_eur"] == 0
    assert k["utci_drop_trail_avg_c"] is None and k["utci_cooled_trail_km"] == 0


def test_trail_utci_drop_weights_cooled_sections_by_length():
    # Unsplit segments, so a linear fix cools exactly that one piece.
    single = [ps[0] for ps in ds.pieces_by_segment.values() if len(ps) == 1]
    short = min(single, key=lambda p: p.length_m)
    long = max(single, key=lambda p: p.length_m)
    junction = first("junction")
    accepted = [("INT-01", short.id), ("INT-04", short.id), ("INT-04", long.id), ("INT-02", junction.id)]
    k = evaluate(ds, "heat", 50_000, accepted)["kpis"]

    pavement_drop = -ds.catalogue["INT-04"]["utci_reduction_c"]
    trees_drop = -ds.catalogue["INT-01"]["utci_reduction_c"]
    short_drop = trees_drop + A["stacking_secondary_factor"] * pavement_drop
    cooled_m = short.length_m + long.length_m
    assert k["utci_cooled_trail_km"] == pytest.approx(cooled_m / 1000)
    assert k["utci_drop_trail_avg_c"] == pytest.approx((short_drop * short.length_m + pavement_drop * long.length_m) / cooled_m)


def test_cooling_a_hot_trail_makes_it_comfortable():
    trail = "TRM-04"  # UTCI 34.5 °C, minus trees 4.5 and half of cool pavement 1.8 = 29.1 < 32
    segs = [ps[0].id for ps in ds.pieces_by_segment.values() if ps[0].trail_id == trail]  # one per real segment
    accepted = [("INT-01", s) for s in segs] + [("INT-04", s) for s in segs]
    k = evaluate(ds, "heat", 1e7, accepted)["kpis"]
    pieces = [p for p in ds.points if p.kind == "segment" and p.trail_id == trail]
    already_km = sum(p.length_m for p in pieces if ds.base_utci[p.id] < A["comfortable_utci_c"]) / 1000
    real_km = ds.trails[trail].raw["real_length_m"] / 1000
    assert math.isclose(k["comfortable_km_gain"], real_km - already_km, abs_tol=1e-3)  # rounded to 0.1 m
    assert k["eur_per_comfortable_km"] is not None
    assert math.isclose(k["adapted_km"], real_km, abs_tol=1e-3)


def test_trees_lift_a_very_hot_piece_out_of_very_strong_heat():
    # TRM-02 is 40.1 °C on average; trees (−4.5 °C) cover the whole real segment. Pick a segment whose
    # pieces are all in very strong heat today and all drop below 38 °C, but stay above 32 °C.
    cut = -ds.catalogue["INT-01"]["utci_reduction_c"]

    def lifted(u: float) -> bool:
        return u >= A["strong_heat_utci_c"] and A["comfortable_utci_c"] <= u - cut < A["strong_heat_utci_c"]

    pieces = next(
        ps for ps in ds.pieces_by_segment.values()
        if ps[0].trail_id == "TRM-02" and all(lifted(ds.base_utci[p.id]) for p in ps)
    )
    k = evaluate(ds, "heat", 1e7, [("INT-01", pieces[0].id)])["kpis"]
    gain = k["after"]["below_strong_heat_km"] - k["before"]["below_strong_heat_km"]
    assert gain == pytest.approx(sum(p.length_m for p in pieces) / 1000)
    assert k["comfortable_km_gain"] == 0


def test_api_endpoints():
    assert client.get("/api/map-data").status_code == 200
    ok = client.post("/api/evaluate", json={"metric": "water", "budget": 50000, "accepted": []})
    assert ok.status_code == 200 and len(ok.json()["worst"]) == 10
    bad = client.post(
        "/api/evaluate", json={"metric": "water", "budget": 100, "accepted": [{"fix_id": "INT-03", "point_id": ok.json()["worst"][0]}]}
    )
    assert bad.status_code == 422 and "budget" in bad.json()["detail"]
    assert client.post("/api/evaluate", json={"metric": "wind", "budget": 1}).status_code == 422


def test_recommendation_reports_impacts_outside_the_selected_metric():
    target = max((p for p in ds.points if p.kind == "segment"), key=lambda p: p.fountain_dist_m)
    response = client.post(
        "/api/recommend", json={"metric": "water", "budget": 100_000, "accepted": [], "point_id": target.id}
    )
    assert response.status_code == 200
    options = {o["fix_id"]: o for o in response.json()["options"]}
    oasis = options["INT-03"]
    assert oasis["status"] == "available"
    impacts = {i["metric"]: i for i in oasis["local_impacts"]}
    assert set(impacts) == {"water", "combined"}  # an oasis adds water only
    assert all(i["before"] > i["after"] for i in impacts.values())
    assert (impacts["water"]["before"], impacts["water"]["after"]) == (oasis["local_before"], oasis["local_after"])
    assert {i["metric"] for i in options["INT-04"]["local_impacts"]} == {"heat", "combined"}


def test_recommendation_reports_measurement_when_score_is_already_zero():
    target = next(p for p in ds.points if p.kind == "segment" and 10 < p.fountain_dist_m < A["water_ok_m"])
    options = recommend(ds, "combined", 100_000, [], target.id)["options"]
    oasis = next(o for o in options if o["fix_id"] == "INT-03")
    water = next(i for i in oasis["local_impacts"] if i["metric"] == "water")
    assert water["before"] == water["after"] == 0
    assert water["measurement"] == {"before": round(target.fountain_dist_m, 1), "after": 0.0, "unit": "m"}


# ---------------------------------------------------------------- scoring fixes


def test_trails_use_cycle_lanes_and_keep_their_vas_r1_ride_time():
    base = baseline_state(ds)
    for tid, trail in ds.trails.items():
        pieces = [p for p in ds.points if p.kind == "segment" and p.trail_id == tid]
        ride_s = sum(exposure_s(ds, p, base[p.id]) for p in pieces)
        assert ride_s == pytest.approx(trail.raw["synthetic_length_m"] / A["cycling_speed_ms"], rel=1e-3)
    # Fraternitat's unclassified ('0') stretches are no longer part of TRM-14.
    assert ds.trails["TRM-14"].raw["real_length_m"] < 1100


def test_green_wave_shortens_the_wait_not_the_temperature():
    junction = max((p for p in ds.points if p.kind == "junction"), key=lambda p: p.wait_s)
    base = baseline_state(ds)
    after = plan_state(ds, [("INT-05", junction.id)])
    assert after[junction.id].utci == base[junction.id].utci
    assert after[junction.id].wait_s == A["green_wave_wait_s"]
    heat = score_point(ds, junction, base[junction.id]).heat
    cut = 1 - burden(ds, junction, after[junction.id], heat) / burden(ds, junction, base[junction.id], heat)
    assert cut == pytest.approx(1 - A["green_wave_wait_s"] / junction.wait_s)


def test_oasis_at_a_station_only_adds_water():
    station = max((p for p in ds.points if p.kind == "station"), key=lambda p: p.fountain_dist_m)
    base = baseline_state(ds)[station.id]
    after = plan_state(ds, [("INT-03", station.id)])[station.id]
    assert (after.utci, after.solar, after.shade_pct, after.wait_s) == (base.utci, base.solar, base.shade_pct, base.wait_s)
    assert after.water_dist_m < base.water_dist_m


def test_combined_uses_the_configured_weights():
    p = first("segment")
    sc = score_point(ds, p, baseline_state(ds)[p.id])
    w = A["weight_water"] + A["weight_sun"] + A["weight_heat"]
    expected = (A["weight_water"] * sc.water + A["weight_sun"] * sc.sun + A["weight_heat"] * sc.heat) / w
    assert sc.combined == pytest.approx(expected)


def test_critical_average_counts_uncooled_points():
    junction = first("junction")
    k = evaluate(ds, "heat", 50_000, [("INT-02", junction.id)])["kpis"]
    drop = -ds.catalogue["INT-02"]["utci_reduction_c"]
    assert k["critical_cooled"] == 1
    assert k["critical_drop_cooled_avg_c"] == pytest.approx(drop)
    assert k["critical_drop_avg_c"] == pytest.approx(drop / k["critical_total"])


def test_junction_fixes_win_back_riders_and_car_share_scales_co2(monkeypatch):
    junction = max((p for p in ds.points if p.kind == "junction"), key=lambda p: p.wait_s)
    k = evaluate(ds, "heat", 50_000, [("INT-05", junction.id)])["kpis"]
    assert k["new_summer_cyclists"] > 0 and k["eur_per_new_cyclist"] is not None
    monkeypatch.setitem(A, "car_trip_share", A["car_trip_share"] / 2)
    half = evaluate(ds, "heat", 50_000, [("INT-05", junction.id)])["kpis"]
    assert half["co2_trips_t_per_year"] == pytest.approx(k["co2_trips_t_per_year"] / 2)
    assert half["eur_saved_per_cyclist_year"] == pytest.approx(k["eur_saved_per_cyclist_year"] / 2)
    assert half["new_summer_cyclists"] == pytest.approx(k["new_summer_cyclists"])


def test_canopy_co2_is_reported_as_avoided_not_sequestered():
    station = first("station")
    k = evaluate(ds, "heat", 50_000, [("INT-06", station.id)])["kpis"]
    assert k["co2_sequestration_t_per_year"] == 0
    assert k["co2_pv_avoided_t_per_year"] == pytest.approx(ds.catalogue["INT-06"]["co2_kg_yr"] / 1000)


def test_auto_plan_beats_every_single_fix():
    budget = 25_000
    plan = auto_plan(ds, "heat", budget, [])["accepted"]
    auto = evaluate(ds, "heat", budget, [(f["fix_id"], f["point_id"]) for f in plan])["burden"]["current"]
    for pid in evaluate(ds, "heat", budget, [])["worst"]:
        for o in recommend(ds, "heat", budget, [], pid)["options"]:
            if o["status"] == "available":
                single = evaluate(ds, "heat", budget, [(o["fix_id"], pid)])["burden"]["current"]
                assert auto <= single + 1e-9
