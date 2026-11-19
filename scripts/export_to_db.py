"""Seed the CyCool database from scripts/data and compute per-segment aggregates.

Loads the municipal layers and the synthetic VAS-R1 tables from CoolCycle_Viladecans.gpkg,
the OpenStreetMap park outlines from osm_parks.geojson (made by fetch_osm_parks.py),
the per-segment solar statistics from bike_solar_screen_geojson.geojson, then computes
segment_metrics in PostGIS (nearest fountain / AMBici / facility distances, rider counts).

The tables are created by the Alembic migrations, so run them first:
    cd backend && alembic upgrade head

Re-runs are safe: rows are upserted, so saved plans are kept. Use --reset to empty every
table before loading (this deletes saved plans).

Usage (from the repo root, database running):
    pip install -r scripts/requirements.txt
    python scripts/export_to_db.py [--data-dir scripts/data] [--reset]

Connection settings come from POSTGRES_* environment variables, then the repo-root .env,
then the same defaults as the backend (postgres/postgres@localhost:5432/app).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import struct
import sys
import uuid
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import psycopg
import yaml
from pyproj import Transformer
import shapely
from shapely.geometry import MultiPolygon, Polygon, shape

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
SRID = 25831

GPKG_NAME = "CoolCycle_Viladecans.gpkg"
TRAIL_MAPPING_FILE = SCRIPTS_DIR / "trail_mapping.yaml"
SOLAR_GEOJSON_NAME = "bike_solar_screen_geojson.geojson"
OSM_PARKS_NAME = "osm_parks.geojson"

DATA_SOURCES = [
    {
        "code": "viladecans_municipal",
        "origin": "municipal",
        "name": "Viladecans 360 open data: cycle network, drinking fountains, AMBici stations, city facilities",
        "url": "https://360.viladecans.cat/",
        "notes": f"Compiled in {GPKG_NAME}",
    },
    {
        "code": "viladecans_solar_2026",
        "origin": "derived",
        "name": "Per-segment statistics of the Viladecans RadiacioSolar2026 raster (10 m buffer, unitless working measure)",
        "url": None,
        "notes": f"Taken from {SOLAR_GEOJSON_NAME}",
    },
    {
        "code": "cycool_derived",
        "origin": "derived",
        "name": "Computed by scripts/export_to_db.py: Euclidean nearest-amenity distances and rider assignment",
        "url": None,
        "notes": None,
    },
    {
        "code": "osm_parks",
        "origin": "external",
        "name": "OpenStreetMap leisure=park polygons (© OpenStreetMap contributors, ODbL)",
        "url": "https://www.openstreetmap.org/copyright",
        "notes": f"Fetched with scripts/fetch_osm_parks.py into {OSM_PARKS_NAME}",
    },
    {
        "code": "vas_r1_synthetic",
        "origin": "synthetic",
        "name": "VAS-R1 'Comfortable cycling routes' challenge dataset (synthetic/demo data, not real Viladecans data)",
        "url": None,
        "notes": f"Tables vas_* in {GPKG_NAME}",
    },
]

# Synthetic routes have no geometry; they are linked to real segments by street name.
# The mapping lives in scripts/trail_mapping.yaml (TRM-13 is left out: no real street match).
# Edit it (or add 'manual' rows to syn_segment_link) to refine the links.
def street_match() -> dict[str, list[str]]:
    return yaml.safe_load(TRAIL_MAPPING_FILE.read_text(encoding="utf-8"))


# How each catalogue entry is costed and where it can be placed (parsed from the unit text).
INTERVENTION_UNITS: dict[str, tuple[str, str]] = {
    "INT-01": ("per_100m", "segment"),   # shade trees, 100 linear metres
    "INT-02": ("per_site", "junction"),  # shade sail at traffic-light waiting box
    "INT-03": ("per_site", "segment"),   # cyclist oasis micro-shelter (incl. fountain)
    "INT-04": ("per_100m", "segment"),   # cool pavement coating, 100 linear metres
    "INT-05": ("per_site", "junction"),  # heat-triggered green wave
    "INT-06": ("per_site", "station"),   # PV canopy over AMBici / Bicibox station
    "INT-07": ("city_wide", "network"),  # route-planner app
    "INT-08": ("reference", "network"),  # modal-shift benchmark, not an intervention
}

DATA_TABLES = [
    "plan_item", "plan", "segment_metrics", "syn_segment_link", "syn_point", "syn_segment", "hourly_profile",
    "intervention_type", "osm_park", "city_facility", "ambici_station", "drinking_fountain", "cycle_segment",
    "data_source",
]


# ---------------------------------------------------------------- helpers
def load_dotenv(path: Path) -> None:
    """Minimal .env reader: sets variables that are not already in the environment."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def conninfo() -> str:
    load_dotenv(REPO_ROOT / ".env")
    return psycopg.conninfo.make_conninfo(
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
        dbname=os.environ.get("POSTGRES_DB", "app"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
    )


def gpkg_wkb(blob: bytes) -> bytes:
    """Strip the GeoPackage binary header and return the standard WKB geometry."""
    if blob[:2] != b"GP":
        raise ValueError("not a GeoPackage geometry blob")
    flags = blob[3]
    envelope_bytes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(flags >> 1) & 0b111]
    srs_id = struct.unpack("<i" if flags & 1 else ">i", blob[4:8])[0]
    if srs_id != SRID:
        raise ValueError(f"unexpected SRS {srs_id}, expected {SRID}")
    return blob[8 + envelope_bytes:]


def gpkg_rows(con: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    cur = con.execute(f'SELECT * FROM "{table}"')
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur]


def to_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value.strip("{}"))


def to_int(value: Any) -> int | None:
    return None if value is None else int(value)


def to_bool_flag(value: Any) -> bool:
    return bool(int(value))


def upsert(cur: psycopg.Cursor, table: str, rows: Sequence[dict[str, Any]], key: str = "id") -> None:
    """INSERT ... ON CONFLICT (key) DO UPDATE for a list of same-shaped dicts.

    A column named 'geom' holds WKB bytes and is converted with ST_GeomFromWKB.
    """
    if not rows:
        return
    cols = list(rows[0])
    values = ", ".join(f"ST_GeomFromWKB(%s, {SRID})" if c == "geom" else "%s" for c in cols)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != key)
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({values}) "
           f"ON CONFLICT ({key}) DO UPDATE SET {updates}")
    cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
    print(f"  {table:<20} {len(rows):>5} rows")


# ---------------------------------------------------------------- loaders
def seed_sources(cur: psycopg.Cursor) -> dict[str, int]:
    upsert(cur, "data_source", DATA_SOURCES, key="code")
    cur.execute("SELECT code, id FROM data_source")
    return dict(cur.fetchall())


def seed_municipal(cur: psycopg.Cursor, gpkg: sqlite3.Connection, source_id: int) -> None:
    upsert(cur, "cycle_segment", [
        {
            "id": r["objectid"],
            "globalid": to_uuid(r["globalid"]),
            "source_id": source_id,
            "idf": to_int(r["idf"]),
            "codvia": r["codvia"],
            "street_name": r["street_name"],
            "cycle_class": r["cycle_class"],
            "is_cycle_candidate": to_bool_flag(r["is_cycle_candidate"]),
            "length_m": r["length_m"],
            "geom": gpkg_wkb(r["geom"]),
        }
        for r in gpkg_rows(gpkg, "bike_network_source")
    ])
    upsert(cur, "drinking_fountain", [
        {
            "id": r["objectid"],
            "globalid": to_uuid(r["globalid"]),
            "source_id": source_id,
            "location_name": r["ubicació"],
            "geom": gpkg_wkb(r["geom"]),
        }
        for r in gpkg_rows(gpkg, "drinking_fountains")
    ])
    upsert(cur, "ambici_station", [
        {
            "id": r["id_estacio"],
            "source_id": source_id,
            "station_num": r["num_estaci"],
            "name": r["nom_estaci"],
            "address": r["address"],
            "bike_racks": r["bike_racks"],
            "geom": gpkg_wkb(r["geom"]),
        }
        for r in gpkg_rows(gpkg, "ambici_stations")
    ])
    upsert(cur, "city_facility", [
        {
            "id": r["fid"],
            "source_id": source_id,
            "name": r["NOMEQUIPAM"],
            "category": r["CATEGORIA"],
            "subcategory": r["SUBCATEGOR"],
            "address": r["ADREÇA"],
            "website": r["WEB"],
            "geom": gpkg_wkb(r["geom"]),
        }
        for r in gpkg_rows(gpkg, "city_facilities")
    ])


def seed_osm_parks(cur: psycopg.Cursor, geojson_path: Path, source_id: int) -> None:
    """OSM park outlines (WGS84 GeoJSON) projected to EPSG:25831."""
    to_utm = Transformer.from_crs(4326, SRID, always_xy=True).transform
    rows = []
    for f in json.loads(geojson_path.read_text(encoding="utf-8"))["features"]:
        geom = shapely.transform(shape(f["geometry"]), to_utm, interleaved=False)
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        rows.append({
            "id": f["properties"]["osm_id"],
            "source_id": source_id,
            "name": f["properties"].get("name"),
            "geom": geom.wkb,
        })
    upsert(cur, "osm_park", rows)


def seed_synthetic(cur: psycopg.Cursor, gpkg: sqlite3.Connection, source_id: int) -> None:
    interventions = []
    for r in gpkg_rows(gpkg, "vas_interventions"):
        if r["intervention_id"] not in INTERVENTION_UNITS:
            raise ValueError(f"No unit mapping for {r['intervention_id']}; add it to INTERVENTION_UNITS")
        unit_kind, applies_to = INTERVENTION_UNITS[r["intervention_id"]]
        interventions.append({
            "id": r["intervention_id"],
            "source_id": source_id,
            "category": r["category"],
            "description": r["solution_description"],
            "unit_label": r["unit"],
            "unit_kind": unit_kind,
            "applies_to": applies_to,
            "capex_eur": r["capex_cost_eur"],
            "opex_eur_yr": r["annual_opex_eur"],
            "surface_temp_reduction_c": r["surface_temp_reduction_c"],
            "utci_improvement_c": r["utci_thermal_comfort_improvement_c"],
            "co2_kg_yr": r["co2_sequestered_or_avoided_kg_yr"],
            "deployment_weeks": r["deployment_time_weeks"],
            "notes": r["notes"],
        })
    upsert(cur, "intervention_type", interventions)

    upsert(cur, "hourly_profile", [
        {
            "hour": r["hour_num"],
            "source_id": source_id,
            "air_temp_c": r["air_temp_viladecans_c"],
            "rel_humidity_pct": r["relative_humidity_pct"],
            "solar_radiation_wm2": r["solar_radiation_wm2"],
            "utci_unshaded_asphalt_c": r["utci_unshaded_asphalt_lane_c"],
            "utci_building_shaded_c": r["utci_building_shaded_street_c"],
            "utci_shaded_park_c": r["utci_shaded_park_greenway_c"],
            "utci_cool_lane_c": r["utci_adapted_cool_lane_c"],
            "cyclist_flow_spring": r["cyclist_flow_spring_baseline"],
            "cyclist_flow_summer": r["cyclist_flow_summer_heatwave"],
        }
        for r in gpkg_rows(gpkg, "vas_hourly_profile")
    ], key="hour")

    upsert(cur, "syn_segment", [
        {
            "id": r["segment_id"],
            "source_id": source_id,
            "name": r["segment_name"],
            "cycleway_type": r["cycleway_type"],
            "length_m": r["length_m"],
            "shade_10am_pct": r["shade_10am_pct"],
            "shade_2pm_pct": r["shade_2pm_pct"],
            "shade_6pm_pct": r["shade_6pm_pct"],
            "pavement_surface": r["pavement_surface"],
            "summer_surface_temp_c": r["summer_surface_temp_c"],
            "utci_2pm_c": r["heat_stress_utci_2pm_c"],
            "daily_cyclists_spring": r["daily_cyclists_spring"],
            "daily_cyclists_summer": r["daily_cyclists_summer"],
            "ridership_drop_pct": r["summer_ridership_drop_pct"],
            "nearest_shelter_id": r["nearest_climate_shelter_id"],
            "thermal_risk_level": r["thermal_risk_level"],
        }
        for r in gpkg_rows(gpkg, "vas_segment_metrics")
    ])

    # Junctions (CRU-*), climate shelters (REF-*) and bike stations (EST-*), at their synthetic coordinates.
    upsert(cur, "syn_point", [
        {
            "id": r["point_id"],
            "source_id": source_id,
            "name": r["point_name"],
            "category": r["category"],
            "syn_segment_id": r["linked_segment_id"],
            "traffic_light_wait_s": r["traffic_light_wait_sec"],
            "shade_pct": r["current_shade_pct"],
            "temp_anomaly_c": r["local_temp_anomaly_c"],
            "notes": r["notes"],
            "geom": gpkg_wkb(r["geom"]),
        }
        for r in gpkg_rows(gpkg, "vas_synthetic_points")
    ])


def link_synthetic_segments(cur: psycopg.Cursor) -> None:
    """Rebuild street-name links; links added by hand ('manual') are kept."""
    cur.execute("DELETE FROM syn_segment_link WHERE match_method = 'street_name'")
    mapping = street_match()
    for syn_id, streets in mapping.items():
        for street in streets:
            cur.execute(
                """INSERT INTO syn_segment_link (syn_segment_id, segment_id, match_method)
                   SELECT %s, id, 'street_name' FROM cycle_segment WHERE street_name = %s
                   ON CONFLICT DO NOTHING""",
                (syn_id, street),
            )
            if cur.rowcount == 0:
                print(f"  warning: {syn_id} street {street!r} matched no segments", file=sys.stderr)
    cur.execute("SELECT count(*), count(DISTINCT syn_segment_id) FROM syn_segment_link")
    links, routes = cur.fetchone()
    print(f"  {'syn_segment_link':<20} {links:>5} rows ({routes} of {len(mapping)} mapped routes linked)")


# ---------------------------------------------------------------- aggregation
def aggregate_distances(cur: psycopg.Cursor) -> None:
    """Euclidean distance from each segment to the nearest fountain, AMBici station and facility."""
    cur.execute(
        """
        INSERT INTO segment_metrics (segment_id, fountain_dist_m, ambici_dist_m, facility_dist_m)
        SELECT s.id, round(f.d::numeric, 1), round(a.d::numeric, 1), round(c.d::numeric, 1)
        FROM cycle_segment s
        CROSS JOIN LATERAL (SELECT ST_Distance(s.geom, x.geom) AS d FROM drinking_fountain x
                            ORDER BY s.geom <-> x.geom LIMIT 1) f
        CROSS JOIN LATERAL (SELECT ST_Distance(s.geom, x.geom) AS d FROM ambici_station x
                            ORDER BY s.geom <-> x.geom LIMIT 1) a
        CROSS JOIN LATERAL (SELECT ST_Distance(s.geom, x.geom) AS d FROM city_facility x
                            ORDER BY s.geom <-> x.geom LIMIT 1) c
        ON CONFLICT (segment_id) DO UPDATE SET
            fountain_dist_m = EXCLUDED.fountain_dist_m,
            ambici_dist_m   = EXCLUDED.ambici_dist_m,
            facility_dist_m = EXCLUDED.facility_dist_m
        """
    )
    print(f"  {'segment_metrics':<20} {cur.rowcount:>5} rows (distances)")


def aggregate_solar(cur: psycopg.Cursor, geojson_path: Path) -> None:
    features = json.loads(geojson_path.read_text(encoding="utf-8"))["features"]
    rows = [
        (
            p["solar_mean_positive"], p["solar_median_positive"], p["solar_max_positive"],
            p["solar_valid_coverage"], p["solar_valid_pixels"], p["solar_class"], p["objectid"],
        )
        for p in (f["properties"] for f in features)
    ]
    cur.executemany(
        """UPDATE segment_metrics SET solar_mean = %s, solar_median = %s, solar_max = %s,
               solar_valid_coverage = %s, solar_valid_pixels = %s, solar_class = %s
           WHERE segment_id = %s""",
        rows,
    )
    cur.execute("SELECT count(*) FROM segment_metrics WHERE solar_mean IS NULL")
    missing = cur.fetchone()[0]
    print(f"  {'segment_metrics':<20} {len(rows):>5} rows (solar), {missing} segments without solar values")


def aggregate_cyclists(cur: psycopg.Cursor) -> None:
    """Riders per segment: synthetic value on matched streets, class median elsewhere (cycle lanes only)."""
    cur.execute("UPDATE segment_metrics SET daily_cyclists_summer = NULL, cyclists_source = NULL")
    cur.execute(
        """
        UPDATE segment_metrics m
        SET daily_cyclists_summer = v.riders, cyclists_source = 'vas_synthetic_match'
        FROM (SELECT l.segment_id, max(s.daily_cyclists_summer) AS riders
              FROM syn_segment_link l JOIN syn_segment s ON s.id = l.syn_segment_id
              GROUP BY l.segment_id) v
        WHERE m.segment_id = v.segment_id
        """
    )
    matched = cur.rowcount
    cur.execute(
        """
        WITH matched AS (
            SELECT c.cycle_class, m.daily_cyclists_summer AS riders
            FROM segment_metrics m JOIN cycle_segment c ON c.id = m.segment_id
            WHERE m.cyclists_source = 'vas_synthetic_match'
        ),
        by_class AS (
            SELECT cycle_class, percentile_cont(0.5) WITHIN GROUP (ORDER BY riders) AS riders
            FROM matched GROUP BY cycle_class
        ),
        overall AS (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY riders) AS riders FROM matched)
        UPDATE segment_metrics m
        SET daily_cyclists_summer = round(coalesce(b.riders, o.riders)),
            cyclists_source = 'class_median_assumed'
        FROM cycle_segment c
        CROSS JOIN overall o
        LEFT JOIN by_class b ON b.cycle_class = c.cycle_class
        WHERE c.id = m.segment_id AND c.is_cycle_candidate AND m.daily_cyclists_summer IS NULL
        """
    )
    print(f"  {'segment_metrics':<20} riders: {matched} from synthetic match, {cur.rowcount} class-median assumed")


# ---------------------------------------------------------------- main
def run(data_dir: Path, reset: bool) -> None:
    gpkg_path = data_dir / GPKG_NAME
    solar_path = data_dir / SOLAR_GEOJSON_NAME
    parks_path = data_dir / OSM_PARKS_NAME
    for path in (gpkg_path, solar_path, parks_path):
        if not path.is_file():
            sys.exit(f"Missing input file: {path}")

    gpkg = sqlite3.connect(f"file:{gpkg_path.as_posix()}?mode=ro", uri=True)
    with psycopg.connect(conninfo()) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('alembic_version') IS NOT NULL AND to_regclass('cycle_segment') IS NOT NULL")
        if not cur.fetchone()[0]:
            sys.exit("Tables not found. Run the migrations first: cd backend && alembic upgrade head")
        if reset:
            print("Emptying tables")
            cur.execute(f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE")

        print("Seeding")
        sources = seed_sources(cur)
        seed_municipal(cur, gpkg, sources["viladecans_municipal"])
        seed_osm_parks(cur, parks_path, sources["osm_parks"])
        seed_synthetic(cur, gpkg, sources["vas_r1_synthetic"])
        link_synthetic_segments(cur)

        print("Aggregating")
        aggregate_distances(cur)
        aggregate_solar(cur, solar_path)
        aggregate_cyclists(cur)
    gpkg.close()
    print("Done")


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=SCRIPTS_DIR / "data", help="folder with the input files")
    parser.add_argument("--reset", action="store_true", help="empty all tables before loading (deletes saved plans)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    run(args.data_dir, args.reset)


if __name__ == "__main__":
    main()
