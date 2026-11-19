"""Loads the planner dataset from PostGIS once per process.

The tables are filled by scripts/export_to_db.py. Everything the planner needs is derived here,
mostly in SQL:
  - trails: the VAS-R1 routes linked to real streets (syn_segment_link, from scripts/trail_mapping.yaml)
  - trail pieces: every real segment on a trail; segments over 100 m are split into ~50 m pieces
  - junctions (CRU-*): snapped from their synthetic coordinates onto their own trail, because
    those coordinates are 140-850 m off the real streets
  - stations: all real AMBici stations at their real location, on or off the trails. Each takes the
    UTCI of the nearest trail and the solar value of the nearest street segment; the two VAS-R1
    stations (EST-B01/B02) are matched to real ones (assumptions.yaml) and add their synthetic data
  - fountains: real municipal fountains, cemetery excluded
  - context network: the rest of the real network, drawn grey
The services then work on this in memory; the API stays stateless.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from sqlalchemy import Connection, text

from app.db.session import engine

APP_DIR = Path(__file__).resolve().parent.parent
ASSUMPTIONS_FILE = APP_DIR / "config" / "assumptions.yaml"

SPLIT_ABOVE_M = 100.0  # segments longer than this are split...
PIECE_TARGET_M = 50.0  # ...into ceil(len / 50) equal pieces
EXCLUDED_CLASSES = ("Carril Bici_En Projecte DIBA",)  # planned, not built
EXCLUDED_FOUNTAIN_LOCATIONS = ("Cementiri",)  # not on cyclists' routes
JUNCTION_CATEGORY = "Critical Traffic Light Junction"
CATALOGUE_IDS = ("INT-01", "INT-02", "INT-03", "INT-04", "INT-05", "INT-06")


@dataclass(frozen=True)
class MapPoint:
    """A clickable location: a piece of trail ("segment"), a junction or a bike station."""

    id: str
    kind: str  # "segment" | "junction" | "station"
    trail_id: str
    street: str
    length_m: float
    solar: float  # real solar value of the segment (assumed W/m²)
    fountain_dist_m: float  # baseline distance to nearest real fountain
    geom: BaseGeometry  # EPSG:25831
    mid: Point  # EPSG:25831, where an oasis would be placed
    raw: dict[str, Any] = field(repr=False)  # full record incl. WGS84 geometry for the client
    wait_s: float = 0.0
    shade_pct: float = 0.0
    temp_anomaly_c: float = 0.0


@dataclass(frozen=True)
class Trail:
    id: str
    raw: dict[str, Any]

    @property
    def utci(self) -> float:
        return float(self.raw["utci_2pm_c"])


@dataclass(frozen=True)
class Dataset:
    points: list[MapPoint]
    points_by_id: dict[str, MapPoint]
    trails: dict[str, Trail]
    fountains: list[dict[str, Any]]
    catalogue: dict[str, dict[str, Any]]
    assumptions: dict[str, Any]
    assumption_list: list[dict[str, Any]]
    context_network: dict[str, Any]
    solar_min: float
    solar_max: float


# ---------------------------------------------------------------- SQL
_PARAMS = {
    "split_above": SPLIT_ABOVE_M,
    "piece_target": PIECE_TARGET_M,
    "excluded_classes": list(EXCLUDED_CLASSES),
    "excluded_fountains": list(EXCLUDED_FOUNTAIN_LOCATIONS),
    "junction_category": JUNCTION_CATEGORY,
    "catalogue_ids": list(CATALOGUE_IDS),
}

# Real segments on a trail (built network only). Shared by the queries below.
_TRAIL_SEGMENTS = """
    trail_segment AS (
        SELECT l.syn_segment_id AS trail_id, s.id, s.street_name, s.cycle_class, s.geom,
               m.solar_mean, ST_Length(s.geom) AS total,
               CASE WHEN ST_Length(s.geom) > :split_above
                    THEN ceil(ST_Length(s.geom) / :piece_target)::int ELSE 1 END AS n
        FROM syn_segment_link l
        JOIN cycle_segment s ON s.id = l.segment_id
        JOIN segment_metrics m ON m.segment_id = s.id
        WHERE s.cycle_class <> ALL(:excluded_classes)
    ),
    fountain AS (
        SELECT geom FROM drinking_fountain
        WHERE coalesce(trim(location_name), '') <> ALL(:excluded_fountains)
    ),
    piece AS (
        SELECT t.trail_id, t.id AS segment_id, t.street_name, t.cycle_class, t.solar_mean, t.n, k,
               CASE WHEN t.n = 1 THEN t.geom
                    ELSE ST_LineSubstring(t.geom, (k - 1)::float8 / t.n, k::float8 / t.n) END AS geom
        FROM trail_segment t
        CROSS JOIN LATERAL generate_series(1, t.n) AS k
    )
"""

_PIECES_SQL = f"""
    WITH {_TRAIL_SEGMENTS}
    SELECT p.trail_id, p.segment_id, p.k, p.n, p.street_name, p.cycle_class,
           ST_Length(p.geom) AS length_m,
           p.solar_mean AS solar,
           ST_AsGeoJSON(p.geom, 2) AS utm,
           ST_AsGeoJSON(ST_Transform(p.geom, 4326), 6) AS wgs,
           ST_AsGeoJSON(ST_LineInterpolatePoint(p.geom, 0.5), 2) AS mid_utm,
           ST_AsGeoJSON(ST_Transform(ST_LineInterpolatePoint(p.geom, 0.5), 4326), 6) AS mid_wgs,
           (SELECT min(ST_Distance(p.geom, f.geom)) FROM fountain f) AS fountain_dist_m
    FROM piece p
    ORDER BY p.segment_id, p.k
"""

# Junctions snapped onto the union of their own trail's segments; the solar value and street come
# from the trail piece nearest to the snapped point.
_JUNCTIONS_SQL = f"""
    WITH {_TRAIL_SEGMENTS},
    trail_line AS (
        SELECT trail_id, ST_Collect(geom) AS geom FROM trail_segment GROUP BY trail_id
    ),
    snapped AS (
        SELECT sp.*, ST_ClosestPoint(tl.geom, sp.geom) AS snap
        FROM syn_point sp
        JOIN trail_line tl ON tl.trail_id = sp.syn_segment_id
        WHERE sp.category = :junction_category
    )
    SELECT s.id, s.syn_segment_id AS trail_id, s.name, s.notes,
           s.traffic_light_wait_s AS wait_s, s.shade_pct, s.temp_anomaly_c,
           ST_Distance(s.geom, s.snap) AS snap_distance_m,
           ST_AsGeoJSON(s.snap, 2) AS utm,
           ST_AsGeoJSON(ST_Transform(s.snap, 4326), 6) AS wgs,
           (SELECT min(ST_Distance(s.snap, f.geom)) FROM fountain f) AS fountain_dist_m,
           near.street_name, near.solar_mean AS solar, near.segment_id, near.k, near.n
    FROM snapped s
    CROSS JOIN LATERAL (
        SELECT p.street_name, p.solar_mean, p.segment_id, p.k, p.n FROM piece p
        WHERE p.trail_id = s.syn_segment_id
        ORDER BY ST_Distance(p.geom, s.snap), p.segment_id, p.k
        LIMIT 1
    ) near
    ORDER BY s.id
"""

# Real AMBici stations at their own location. The nearest trail piece gives the trail (whose
# synthetic UTCI the station takes); the nearest street segment of the built network gives the
# real solar value and the street.
_STATIONS_SQL = f"""
    WITH {_TRAIL_SEGMENTS}
    SELECT a.station_num, a.name, a.address, a.bike_racks,
           ST_AsGeoJSON(a.geom, 2) AS utm,
           ST_AsGeoJSON(ST_Transform(a.geom, 4326), 6) AS wgs,
           (SELECT min(ST_Distance(a.geom, f.geom)) FROM fountain f) AS fountain_dist_m,
           trail.trail_id, trail.dist AS trail_dist_m,
           street.id AS solar_segment_id, street.street_name, street.solar_mean AS solar
    FROM ambici_station a
    CROSS JOIN LATERAL (
        SELECT p.trail_id, ST_Distance(p.geom, a.geom) AS dist FROM piece p
        ORDER BY ST_Distance(p.geom, a.geom), p.segment_id, p.k
        LIMIT 1
    ) trail
    CROSS JOIN LATERAL (
        SELECT s.id, s.street_name, m.solar_mean FROM cycle_segment s
        JOIN segment_metrics m ON m.segment_id = s.id
        WHERE s.cycle_class <> ALL(:excluded_classes)
        ORDER BY ST_Distance(s.geom, a.geom), s.id
        LIMIT 1
    ) street
    ORDER BY a.station_num
"""

# Synthetic data of the VAS-R1 stations that are matched to real ones.
_VAS_STATIONS_SQL = """
    SELECT id, shade_pct, temp_anomaly_c, notes FROM syn_point WHERE id = ANY(:vas_station_ids)
"""

_TRAILS_SQL = """
    SELECT t.id, t.name, t.cycleway_type, t.length_m AS synthetic_length_m, t.utci_2pm_c,
           t.summer_surface_temp_c AS surface_temp_c, t.shade_2pm_pct,
           t.nearest_shelter_id, shelter.name AS nearest_shelter_name, t.thermal_risk_level AS risk_level,
           array_agg(DISTINCT s.street_name ORDER BY s.street_name) AS streets
    FROM syn_segment t
    JOIN syn_segment_link l ON l.syn_segment_id = t.id
    JOIN cycle_segment s ON s.id = l.segment_id
    LEFT JOIN syn_point shelter ON shelter.id = t.nearest_shelter_id
    WHERE s.cycle_class <> ALL(:excluded_classes)
    GROUP BY t.id, shelter.name
    ORDER BY t.id
"""

_FOUNTAINS_SQL = """
    SELECT id, nullif(trim(location_name), '') AS location,
           ST_AsGeoJSON(geom, 2) AS utm, ST_AsGeoJSON(ST_Transform(geom, 4326), 6) AS wgs
    FROM drinking_fountain
    WHERE coalesce(trim(location_name), '') <> ALL(:excluded_fountains)
    ORDER BY id
"""

_CONTEXT_SQL = """
    SELECT s.is_cycle_candidate AS cycle,
           ST_AsGeoJSON(ST_Transform(ST_SimplifyPreserveTopology(s.geom, 1.0), 4326), 6) AS geometry
    FROM cycle_segment s
    WHERE s.cycle_class <> ALL(:excluded_classes)
      AND NOT EXISTS (SELECT 1 FROM syn_segment_link l WHERE l.segment_id = s.id)
    ORDER BY s.id
"""

_CATALOGUE_SQL = """
    SELECT id, category, description, unit_label AS unit, capex_eur, opex_eur_yr,
           surface_temp_reduction_c, utci_improvement_c AS utci_reduction_c, co2_kg_yr,
           deployment_weeks, notes
    FROM intervention_type
    WHERE id = ANY(:catalogue_ids)
    ORDER BY id
"""


# ---------------------------------------------------------------- helpers
def _coords(geojson: str) -> list[list[float]]:
    """GeoJSON LineString/Point -> list of [x, y] (EPSG:25831) or [lon, lat]."""
    geom = json.loads(geojson)
    return geom["coordinates"] if geom["type"] == "LineString" else [geom["coordinates"]]


def _latlon(geojson: str) -> list[list[float]]:
    return [[lat, lon] for lon, lat in _coords(geojson)]


def _piece_id(segment_id: int, k: int, n: int) -> str:
    return f"{segment_id}-{k}" if n > 1 else str(segment_id)


def _num(value: Any, digits: int | None = None) -> float:
    return float(value) if digits is None else round(float(value), digits)


def _to_point(rec: dict[str, Any]) -> MapPoint:
    coords = rec["utm"]
    geom: BaseGeometry = LineString(coords) if len(coords) > 1 else Point(coords[0])
    return MapPoint(
        id=rec["id"],
        kind=rec["kind"],
        trail_id=rec["trail_id"],
        street=rec["street"],
        length_m=float(rec["length_m"]),
        solar=float(rec["solar"]),
        fountain_dist_m=float(rec["fountain_dist_m"]),
        geom=geom,
        mid=Point(rec["mid_utm"]),
        raw=rec,
        wait_s=float(rec.get("wait_s", 0.0)),
        shade_pct=float(rec.get("shade_pct", 0.0)),
        temp_anomaly_c=float(rec.get("temp_anomaly_c", 0.0)),
    )


def _rows(conn: Connection, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(text(sql), {**_PARAMS, **params}).mappings()]


def _vas_station_matches(assumptions: dict[str, Any]) -> dict[int, str]:
    """{real AMBici station number: VAS-R1 station id}, from entries like "EST-B01 → 34863"."""
    matches = {}
    for entry in assumptions["vas_station_match"]:
        vas_id, station_num = (part.strip() for part in entry.split("→"))
        matches[int(station_num)] = vas_id
    return matches


# ---------------------------------------------------------------- loaders
def _load_pieces(conn: Connection) -> list[dict[str, Any]]:
    pieces = []
    for r in _rows(conn, _PIECES_SQL):
        pieces.append(
            {
                "id": _piece_id(r["segment_id"], r["k"], r["n"]),
                "kind": "segment",
                "trail_id": r["trail_id"],
                "street": r["street_name"],
                "cycle_class": r["cycle_class"],
                "length_m": _num(r["length_m"], 2),
                "solar": _num(r["solar"], 1),
                "utm": _coords(r["utm"]),
                "mid_utm": _coords(r["mid_utm"])[0],
                "wgs": _latlon(r["wgs"]),
                "mid_wgs": _latlon(r["mid_wgs"])[0],
                "fountain_dist_m": _num(r["fountain_dist_m"], 1),
            }
        )
    return pieces


def _load_junctions(conn: Connection) -> list[dict[str, Any]]:
    points = []
    for r in _rows(conn, _JUNCTIONS_SQL):
        utm, wgs = _coords(r["utm"]), _latlon(r["wgs"])
        points.append(
            {
                "id": r["id"],
                "kind": "junction",
                "trail_id": r["trail_id"],
                "street": r["street_name"],
                "name": r["name"],
                "notes": r["notes"],
                "length_m": 0.0,
                "solar": _num(r["solar"], 1),  # real solar of the trail segment it sits on
                "solar_from": _piece_id(r["segment_id"], r["k"], r["n"]),
                "wait_s": _num(r["wait_s"]),
                "shade_pct": _num(r["shade_pct"]),
                "temp_anomaly_c": _num(r["temp_anomaly_c"]),
                "utm": utm,
                "mid_utm": utm[0],
                "wgs": wgs,
                "mid_wgs": wgs[0],
                "snap_distance_m": _num(r["snap_distance_m"], 1),
                "fountain_dist_m": _num(r["fountain_dist_m"], 1),
            }
        )
    return points


def _load_stations(conn: Connection, matches: dict[int, str]) -> list[dict[str, Any]]:
    vas = {r["id"]: r for r in _rows(conn, _VAS_STATIONS_SQL, vas_station_ids=list(matches.values()))}
    stations = []
    for r in _rows(conn, _STATIONS_SQL):
        utm, wgs = _coords(r["utm"]), _latlon(r["wgs"])
        station = {
            "id": f"AMB-{r['station_num']}",
            "kind": "station",
            "trail_id": r["trail_id"],  # nearest trail: the station takes its synthetic UTCI
            "street": r["street_name"],
            "name": r["name"],
            "address": r["address"],
            "bike_racks": r["bike_racks"],
            "length_m": 0.0,
            "solar": _num(r["solar"], 1),  # real solar of the nearest street segment
            "solar_from": str(r["solar_segment_id"]),
            "utm": utm,
            "mid_utm": utm[0],
            "wgs": wgs,
            "mid_wgs": wgs[0],
            "trail_dist_m": _num(r["trail_dist_m"], 1),
            "fountain_dist_m": _num(r["fountain_dist_m"], 1),
        }
        syn = vas.get(matches.get(r["station_num"], ""))
        if syn:
            station.update(
                vas_id=syn["id"],
                notes=syn["notes"],
                shade_pct=_num(syn["shade_pct"]),
                temp_anomaly_c=_num(syn["temp_anomaly_c"]),
            )
        stations.append(station)
    return stations


def _load_trails(conn: Connection, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trails = []
    for r in _rows(conn, _TRAILS_SQL):
        real_len = sum(p["length_m"] for p in points if p["trail_id"] == r["id"] and p["kind"] == "segment")
        trails.append(
            {
                "id": r["id"],
                "name": r["name"],
                "streets": list(r["streets"]),
                "cycleway_type": r["cycleway_type"],
                "real_length_m": round(real_len, 1),
                "synthetic_length_m": _num(r["synthetic_length_m"]),
                "utci_2pm_c": _num(r["utci_2pm_c"]),
                "surface_temp_c": _num(r["surface_temp_c"]),
                "shade_2pm_pct": _num(r["shade_2pm_pct"]),
                "nearest_shelter_id": r["nearest_shelter_id"],
                "nearest_shelter_name": r["nearest_shelter_name"],
                "risk_level": r["risk_level"],
            }
        )
    return trails


def _load_fountains(conn: Connection) -> list[dict[str, Any]]:
    return [
        {"id": f"F-{r['id']}", "location": r["location"], "utm": _coords(r["utm"])[0], "wgs": _latlon(r["wgs"])[0]}
        for r in _rows(conn, _FOUNTAINS_SQL)
    ]


def _load_context(conn: Connection) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"cycle": bool(r["cycle"])}, "geometry": json.loads(r["geometry"])}
            for r in _rows(conn, _CONTEXT_SQL)
        ],
    }


def _load_catalogue(conn: Connection) -> dict[str, dict[str, Any]]:
    numeric = ("capex_eur", "opex_eur_yr", "surface_temp_reduction_c", "utci_reduction_c", "co2_kg_yr", "deployment_weeks")
    catalogue = {}
    for r in _rows(conn, _CATALOGUE_SQL):
        catalogue[r["id"]] = {**r, **{k: _num(r[k] or 0) for k in numeric}}
    return catalogue


def _check(
    trails: list[dict[str, Any]], points: list[dict[str, Any]], catalogue: dict[str, Any], matches: dict[int, str]
) -> None:
    """Fail loudly on an unseeded or half-seeded database instead of serving an empty map."""
    problems = []
    if not trails:
        problems.append("no trails (syn_segment_link is empty)")
    if not any(p["kind"] == "segment" for p in points):
        problems.append("no trail segments")
    if not any(p["kind"] == "station" for p in points):
        problems.append("no AMBici stations")
    unmatched = sorted(set(matches.values()) - {p.get("vas_id") for p in points})
    if unmatched:
        problems.append(f"VAS-R1 stations without their real AMBici station: {', '.join(unmatched)}")
    missing = sorted(set(CATALOGUE_IDS) - set(catalogue))
    if missing:
        problems.append(f"catalogue entries missing: {', '.join(missing)}")
    empty = [t["id"] for t in trails if not any(p["trail_id"] == t["id"] for p in points)]
    if empty:
        problems.append(f"trails without points: {', '.join(empty)}")
    if problems:
        raise RuntimeError(
            "The database is not seeded for the planner: " + "; ".join(problems)
            + ". Run: python scripts/export_to_db.py"
        )


def load_dataset() -> Dataset:
    assumption_list = yaml.safe_load(ASSUMPTIONS_FILE.read_text(encoding="utf-8"))
    assumptions = {a["key"]: a["value"] for a in assumption_list}
    matches = _vas_station_matches(assumptions)
    with engine.connect() as conn:
        pieces = _load_pieces(conn)
        points_raw = pieces + _load_junctions(conn) + _load_stations(conn, matches)
        trails_raw = _load_trails(conn, points_raw)
        fountains = _load_fountains(conn)
        context = _load_context(conn)
        catalogue = _load_catalogue(conn)
    _check(trails_raw, points_raw, catalogue, matches)

    points = [_to_point(r) for r in points_raw]
    segment_solar = [p.solar for p in points if p.kind == "segment"]
    return Dataset(
        points=points,
        points_by_id={p.id: p for p in points},
        trails={t["id"]: Trail(id=t["id"], raw=t) for t in trails_raw},
        fountains=fountains,
        catalogue=catalogue,
        assumptions=assumptions,
        assumption_list=assumption_list,
        context_network=context,
        solar_min=min(segment_solar),
        solar_max=max(segment_solar),
    )


@lru_cache(maxsize=1)
def get_dataset() -> Dataset:
    return load_dataset()
