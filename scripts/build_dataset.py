"""Build the prototype dataset consumed by the backend (backend/app/data/*.json).

Inputs (from the hackathon Data/ folder, default ../../Data relative to this file):
  - bike_solar_screen_geojson.geojson   real network segments + real solar value (EPSG:25831)
  - Fonts_de_Beure_(Dades)/*.shp        real drinking fountains (EPSG:25831)
  - VAS_R1_Dataset_.../*.csv            synthetic VAS-R1 trails, junctions/stations, catalogue
  - scripts/trail_mapping.yaml          VAS-R1 trail id -> real street names

Run:  python scripts/build_dataset.py [--data-dir PATH]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import shapefile  # pyshp
import yaml
from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import nearest_points, substring, unary_union

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "backend" / "app" / "data"
MAPPING_FILE = Path(__file__).resolve().parent / "trail_mapping.yaml"
VAS_DIR_NAME = "VAS_R1_Dataset_Climate_Shelters_and_Cycling_EN"

SPLIT_ABOVE_M = 100.0  # segments longer than this are split...
PIECE_TARGET_M = 50.0  # ...into ceil(len / 50) equal pieces
EXCLUDED_CLASSES = {"Carril Bici_En Projecte DIBA"}  # planned, not built
EXCLUDED_FOUNTAIN_LOCATIONS = {"Cementiri"}  # not on cyclists' routes
LOCATED_KINDS = {"Critical Traffic Light Junction": "junction"}
STATION_IDS = {"EST-B01", "EST-B02"}
CATALOGUE_IDS = ["INT-01", "INT-02", "INT-03", "INT-04", "INT-05", "INT-06"]

to_wgs = Transformer.from_crs("EPSG:25831", "EPSG:4326", always_xy=True)
from_wgs = Transformer.from_crs("EPSG:4326", "EPSG:25831", always_xy=True)


def latlon(x: float, y: float) -> list[float]:
    lon, lat = to_wgs.transform(x, y)
    return [round(lat, 6), round(lon, 6)]


def rnd(coords) -> list[list[float]]:
    return [[round(x, 2), round(y, 2)] for x, y in coords]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(value: str) -> float:
    return float(value)


def build(data_dir: Path) -> None:
    vas_dir = data_dir / VAS_DIR_NAME
    mapping: dict[str, list[str]] = yaml.safe_load(MAPPING_FILE.read_text(encoding="utf-8"))
    street_to_trail = {street: tid for tid, streets in mapping.items() for street in streets}

    # ---------- VAS-R1 synthetic trails ----------
    seg_rows = {r["segment_id"]: r for r in read_csv(vas_dir / "vas_r1_cycling_network_climate_segments.csv")}
    node_rows = read_csv(vas_dir / "vas_r1_junctions_shelters_and_stations.csv")
    shelter_names = {r["point_id"]: r["point_name"] for r in node_rows if r["point_id"].startswith("REF-")}
    missing = [t for t in mapping if t not in seg_rows]
    if missing:
        raise SystemExit(f"Trail ids in mapping not found in VAS-R1 CSV: {missing}")

    # ---------- real network ----------
    network = json.loads((data_dir / "bike_solar_screen_geojson.geojson").read_text(encoding="utf-8"))
    points: list[dict] = []
    context: list[dict] = []
    trail_lines: dict[str, list[LineString]] = {t: [] for t in mapping}
    excluded_planned = 0
    for feat in network["features"]:
        props = feat["properties"]
        geom = shape(feat["geometry"])
        if props.get("cycle_class") in EXCLUDED_CLASSES:
            excluded_planned += 1
            continue
        trail_id = street_to_trail.get(props.get("street_name"))
        if trail_id is None:
            simple = geom.simplify(1.0)
            context.append(
                {
                    "type": "Feature",
                    "properties": {"cycle": bool(props.get("is_cycle_candidate"))},
                    "geometry": {"type": "LineString", "coordinates": [latlon(x, y)[::-1] for x, y in simple.coords]},
                }
            )
            continue
        if not isinstance(geom, LineString):
            raise SystemExit(f"Unexpected geometry {geom.geom_type} for fid {props['fid']}")
        trail_lines[trail_id].append(geom)
        total = geom.length
        n = math.ceil(total / PIECE_TARGET_M) if total > SPLIT_ABOVE_M else 1
        for k in range(n):
            piece = substring(geom, total * k / n, total * (k + 1) / n) if n > 1 else geom
            mid = piece.interpolate(0.5, normalized=True)
            points.append(
                {
                    "id": f"{props['fid']}-{k + 1}" if n > 1 else str(props["fid"]),
                    "kind": "segment",
                    "trail_id": trail_id,
                    "street": props["street_name"],
                    "cycle_class": props["cycle_class"],
                    "length_m": round(piece.length, 2),
                    "solar": round(float(props["solar_mean_positive"]), 1),
                    "utm": rnd(piece.coords),
                    "mid_utm": [round(mid.x, 2), round(mid.y, 2)],
                    "wgs": [latlon(x, y) for x, y in piece.coords],
                    "mid_wgs": latlon(mid.x, mid.y),
                }
            )

    empty = [t for t, lines in trail_lines.items() if not lines]
    if empty:
        raise SystemExit(f"Trails with no matched segments: {empty}")

    # ---------- junctions & stations: snap onto their own linked trail ----------
    segment_points = [p for p in points if p["kind"] == "segment"]
    snap_report = []
    for row in node_rows:
        pid = row["point_id"]
        kind = LOCATED_KINDS.get(row["category"]) or ("station" if pid in STATION_IDS else None)
        if kind is None:
            continue  # shelters are not map points (decision: only named in point details)
        trail_id = row["linked_segment_id"]
        if trail_id not in trail_lines:
            raise SystemExit(f"{pid} links to unmapped trail {trail_id}")
        x, y = from_wgs.transform(num(row["longitude"]), num(row["latitude"]))
        original = Point(x, y)
        snapped = nearest_points(unary_union(trail_lines[trail_id]), original)[0]
        snap_distance = original.distance(snapped)
        nearest_seg = min(
            (p for p in segment_points if p["trail_id"] == trail_id),
            key=lambda p: LineString(p["utm"]).distance(snapped),
        )
        points.append(
            {
                "id": pid,
                "kind": kind,
                "trail_id": trail_id,
                "street": nearest_seg["street"],
                "name": row["point_name"],
                "notes": row["notes"],
                "length_m": 0.0,
                "solar": nearest_seg["solar"],  # real solar of the trail segment it sits on
                "solar_from": nearest_seg["id"],
                "wait_s": num(row["traffic_light_wait_sec"]),
                "shade_pct": num(row["current_shade_pct"]),
                "temp_anomaly_c": num(row["local_temp_anomaly_c"]),
                "utm": [[round(snapped.x, 2), round(snapped.y, 2)]],
                "mid_utm": [round(snapped.x, 2), round(snapped.y, 2)],
                "wgs": [latlon(snapped.x, snapped.y)],
                "mid_wgs": latlon(snapped.x, snapped.y),
                "snap_distance_m": round(snap_distance, 1),
            }
        )
        snap_report.append({"id": pid, "trail_id": trail_id, "snap_distance_m": round(snap_distance, 1)})

    # ---------- fountains (real) ----------
    reader = shapefile.Reader(str(next((data_dir / "Fonts_de_Beure_(Dades)").glob("*.shp"))), encoding="utf-8")
    field_names = [f[0] for f in reader.fields[1:]]
    fountains = []
    excluded_fountains = 0
    for shp, rec in zip(reader.shapes(), reader.records()):
        attrs = dict(zip(field_names, rec))
        location = (attrs.get("ubicació") or "").strip()
        if location in EXCLUDED_FOUNTAIN_LOCATIONS:
            excluded_fountains += 1
            continue
        fx, fy = shp.points[0]
        fountains.append(
            {"id": f"F-{attrs['objectid']}", "location": location or None, "utm": [round(fx, 2), round(fy, 2)], "wgs": latlon(fx, fy)}
        )

    # baseline distance from each point geometry to the nearest real fountain
    fountain_geoms = [Point(f["utm"]) for f in fountains]
    for p in points:
        geom = LineString(p["utm"]) if len(p["utm"]) > 1 else Point(p["utm"][0])
        p["fountain_dist_m"] = round(min(geom.distance(fg) for fg in fountain_geoms), 1)

    # ---------- trails ----------
    trails = []
    for tid, streets in mapping.items():
        r = seg_rows[tid]
        real_len = sum(p["length_m"] for p in points if p["trail_id"] == tid and p["kind"] == "segment")
        trails.append(
            {
                "id": tid,
                "name": r["segment_name"],
                "streets": streets,
                "cycleway_type": r["cycleway_type"],
                "real_length_m": round(real_len, 1),
                "synthetic_length_m": num(r["length_m"]),
                "utci_2pm_c": num(r["heat_stress_utci_2pm_c"]),
                "surface_temp_c": num(r["summer_surface_temp_c"]),
                "shade_2pm_pct": num(r["shade_2pm_pct"]),
                "nearest_shelter_id": r["nearest_climate_shelter_id"],
                "nearest_shelter_name": shelter_names.get(r["nearest_climate_shelter_id"]),
                "risk_level": r["thermal_risk_level"],
            }
        )

    # ---------- catalogue (INT-01..06) ----------
    catalogue = []
    for r in read_csv(vas_dir / "vas_r1_cycling_comfort_interventions_catalog.csv"):
        if r["intervention_id"] not in CATALOGUE_IDS:
            continue
        catalogue.append(
            {
                "id": r["intervention_id"],
                "category": r["category"],
                "description": r["solution_description"],
                "unit": r["unit"],
                "capex_eur": num(r["capex_cost_eur"]),
                "opex_eur_yr": num(r["annual_opex_eur"]),
                "surface_temp_reduction_c": num(r["surface_temp_reduction_c"]),
                "utci_reduction_c": num(r["utci_thermal_comfort_improvement_c"]),
                "co2_kg_yr": num(r["co2_sequestered_or_avoided_kg_yr"]),
                "deployment_weeks": num(r["deployment_time_weeks"]),
                "notes": r["notes"],
            }
        )
    modal = next(
        r for r in read_csv(vas_dir / "vas_r1_cycling_comfort_interventions_catalog.csv") if r["intervention_id"] == "INT-08"
    )

    # ---------- write ----------
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    def dump(name: str, obj) -> None:
        (OUT_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    dump("points.json", points)
    dump("trails.json", trails)
    dump("fountains.json", fountains)
    dump("catalogue.json", {"interventions": catalogue, "modal_shift_reference": modal})
    dump("context_network.geojson", {"type": "FeatureCollection", "features": context})
    report = {
        "trails": len(trails),
        "segment_points": sum(1 for p in points if p["kind"] == "segment"),
        "junction_points": sum(1 for p in points if p["kind"] == "junction"),
        "station_points": sum(1 for p in points if p["kind"] == "station"),
        "trail_km_real": round(sum(t["real_length_m"] for t in trails) / 1000, 2),
        "km_per_trail": {t["id"]: round(t["real_length_m"] / 1000, 3) for t in trails},
        "excluded_planned_segments": excluded_planned,
        "fountains_used": len(fountains),
        "fountains_excluded_cemetery": excluded_fountains,
        "context_segments": len(context),
        "snaps": snap_report,
    }
    (OUT_DIR / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT.parent / "Data")
    build(parser.parse_args().data_dir)
