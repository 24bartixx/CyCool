"""Loads the planner dataset from PostGIS once per process.

The tables are filled by scripts/export_to_db.py. Everything the planner needs is derived here,
mostly in SQL:
  - trails: the VAS-R1 routes linked to real streets (syn_segment_link, from scripts/trail_mapping.yaml),
    with their synthetic UTCI and rider counts
  - pieces: every built segment of the real network, split into ~50 m pieces when over 100 m. A piece is on
    a trail when its segment is one of the trail's cycle-lane segments on its matched streets (a matched
    street with no cycle-lane segment, e.g. a cycle street in a pedestrian zone or a park path, is taken
    whole); every other piece has no trail and takes the assumed riders of its segment (segment_metrics)
  - junctions (CRU-*): placed at the real feature named in their VAS-R1 name (config/point_anchors.yaml),
    because their synthetic coordinates are 140-850 m off the real streets
  - stations: all real AMBici stations at their real location. Each takes the solar index and Landsat
    surface temperature of the nearest street segment and the riders of the nearest trail; the two VAS-R1
    stations (EST-B01/B02) are matched to real ones (assumptions.yaml) and carry their synthetic notes
  - fountains: real municipal fountains, cemetery excluded
  - parks (OpenStreetMap outlines) and Bicibox bike parkings (municipal facilities): display-only map layers
  - surface temperature: Landsat 8/9 summer land surface temperature on every built segment; an input of
    the UTCI model, also returned to the client as `surface_temp`
  - sun anchors: percentiles of the solar index over the whole built network
  - design weather: the hot-day summer afternoon from the real hourly weather (weather_hour)
  - UTCI: computed per piece and station from the design weather, the share of direct sun (solar index)
    and the ground temperature (Landsat) by services/heat_model.py; junctions keep the synthetic VAS-R1
    value (trail UTCI plus their local anomaly)
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
from app.services.heat_model import DesignWeather, design_weather, place_heat

APP_DIR = Path(__file__).resolve().parent.parent
ASSUMPTIONS_FILE = APP_DIR / "config" / "assumptions.yaml"
ANCHORS_FILE = APP_DIR / "config" / "point_anchors.yaml"

SPLIT_ABOVE_M = 100.0  # segments longer than this are split...
PIECE_TARGET_M = 50.0  # ...into ceil(len / 50) equal pieces
EXCLUDED_CLASSES = ("Carril Bici_En Projecte DIBA",)  # planned, not built
EXCLUDED_FOUNTAIN_LOCATIONS = ("Cementiri",)  # not on cyclists' routes
BIKE_PARKING = ("Transport", "Estacions Bicibox")  # municipal facility (category, subcategory)
JUNCTION_CATEGORY = "Critical Traffic Light Junction"
CATALOGUE_IDS = ("INT-01", "INT-02", "INT-03", "INT-04", "INT-05", "INT-06")
MODAL_SHIFT_ID = "INT-08"  # not a fix: CO2 and € per replaced trip, used by the KPIs


@dataclass(frozen=True)
class MapPoint:
    """A clickable location: a piece of a network segment ("segment"), a junction or a bike station."""

    id: str
    kind: str  # "segment" | "junction" | "station"
    trail_id: str | None  # VAS-R1 trail of a piece (None off the trails); the nearest trail of a station
    street: str
    length_m: float
    solar: float  # real solar index of the segment (unit not stated in the source)
    fountain_dist_m: float  # baseline distance to nearest real fountain
    geom: BaseGeometry  # EPSG:25831
    mid: Point  # EPSG:25831, where an oasis would be placed
    raw: dict[str, Any] = field(repr=False)  # full record incl. WGS84 geometry for the client
    segment_id: str | None = None  # real network segment a piece belongs to
    lst_c: float | None = None  # Landsat summer surface temperature (own segment, or nearest for a station)
    riders_day: float = 0.0  # pieces: riders/day the ranking and burden use (see metric_service.riders)
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

    @property
    def riders_spring(self) -> float:
        return float(self.raw["riders_spring"])

    @property
    def riders_summer(self) -> float:
        return float(self.raw["riders_summer"])

    @property
    def synthetic_length_km(self) -> float:
        return float(self.raw["synthetic_length_m"]) / 1000

    @property
    def length_scale(self) -> float:
        """VAS-R1 length / matched real length: scales ride time so a trail's total matches its synthetic route."""
        real = float(self.raw["real_length_m"])
        return self.synthetic_length_km * 1000 / real if real > 0 else 1.0

    @property
    def critical(self) -> bool:
        return str(self.raw.get("risk_level") or "").startswith("Critical")


@dataclass(frozen=True)
class Dataset:
    points: list[MapPoint]
    points_by_id: dict[str, MapPoint]
    pieces_by_segment: dict[str, list[MapPoint]]
    trails: dict[str, Trail]
    fountains: list[dict[str, Any]]
    catalogue: dict[str, dict[str, Any]]
    modal_shift: dict[str, Any]
    assumptions: dict[str, Any]
    assumption_list: list[dict[str, Any]]
    parks: dict[str, Any]  # GeoJSON FeatureCollection of OSM park outlines (WGS84), display only
    bike_parkings: list[dict[str, Any]]  # Bicibox secure bike parkings, display only
    surface_temp: dict[str, Any]  # GeoJSON of built segments with Landsat summer LST (°C)
    solar_min: float  # sun score 0 (low percentile of the whole built network)
    solar_max: float  # sun score 1 (high percentile of the whole built network)
    weather: DesignWeather  # the hot summer afternoon the UTCI model is evaluated for
    off_trail_spring_ratio: float  # spring / summer riders over the trails, applied to off-trail pieces
    base_utci: dict[str, float]  # baseline UTCI per point


# ---------------------------------------------------------------- SQL
_PARAMS = {
    "split_above": SPLIT_ABOVE_M,
    "piece_target": PIECE_TARGET_M,
    "excluded_classes": list(EXCLUDED_CLASSES),
    "excluded_fountains": list(EXCLUDED_FOUNTAIN_LOCATIONS),
    "junction_category": JUNCTION_CATEGORY,
    "catalogue_ids": [*CATALOGUE_IDS, MODAL_SHIFT_ID],
    "bike_parking_category": BIKE_PARKING[0],
    "bike_parking_subcategory": BIKE_PARKING[1],
}

# Real segments that make up a trail: the built cycle-lane segments on its matched streets. A street match
# also picks up pavements, pedestrian zones and unclassified stretches ('0', 'NO') of streets that do have
# a cycle lane, which made some trails up to 2.8x longer than the VAS-R1 route. A matched street with no
# cycle-lane segment at all (a cycle street in a pedestrian zone, a park path) is taken whole.
_TRAIL_LINK = """
    linked AS (
        SELECT l.syn_segment_id AS trail_id, s.id AS segment_id, s.street_name, s.is_cycle_candidate
        FROM syn_segment_link l JOIN cycle_segment s ON s.id = l.segment_id
        WHERE s.cycle_class <> ALL(:excluded_classes)
    ),
    trail_link AS (
        SELECT a.trail_id, a.segment_id FROM linked a
        WHERE a.is_cycle_candidate
           OR NOT EXISTS (
               SELECT 1 FROM linked b
               WHERE b.trail_id = a.trail_id AND b.street_name = a.street_name AND b.is_cycle_candidate
           )
    )
"""

# Real segments on a trail. Shared by the queries below.
_TRAIL_SEGMENTS = f"""
    {_TRAIL_LINK},
    trail_segment AS (
        SELECT l.trail_id, s.id, s.street_name, s.cycle_class, s.geom,
               m.solar_mean, ST_Length(s.geom) AS total,
               CASE WHEN ST_Length(s.geom) > :split_above
                    THEN ceil(ST_Length(s.geom) / :piece_target)::int ELSE 1 END AS n
        FROM trail_link l
        JOIN cycle_segment s ON s.id = l.segment_id
        JOIN segment_metrics m ON m.segment_id = s.id
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

# Every built segment of the network, split like the trail segments; trail_id is NULL off the trails.
_PIECES_SQL = f"""
    WITH {_TRAIL_LINK},
    network_segment AS (
        SELECT l.trail_id, s.id, s.street_name, s.cycle_class, s.geom,
               m.solar_mean, m.lst_summer_c, m.daily_cyclists_summer,
               CASE WHEN ST_Length(s.geom) > :split_above
                    THEN ceil(ST_Length(s.geom) / :piece_target)::int ELSE 1 END AS n
        FROM cycle_segment s
        JOIN segment_metrics m ON m.segment_id = s.id
        LEFT JOIN trail_link l ON l.segment_id = s.id
        WHERE s.cycle_class <> ALL(:excluded_classes)
    ),
    fountain AS (
        SELECT geom FROM drinking_fountain
        WHERE coalesce(trim(location_name), '') <> ALL(:excluded_fountains)
    ),
    piece AS (
        SELECT t.trail_id, t.id AS segment_id, t.street_name, t.cycle_class, t.solar_mean, t.lst_summer_c,
               t.daily_cyclists_summer, t.n, k,
               CASE WHEN t.n = 1 THEN t.geom
                    ELSE ST_LineSubstring(t.geom, (k - 1)::float8 / t.n, k::float8 / t.n) END AS geom
        FROM network_segment t
        CROSS JOIN LATERAL generate_series(1, t.n) AS k
    )
    SELECT p.trail_id, p.segment_id, p.k, p.n, p.street_name, p.cycle_class,
           ST_Length(p.geom) AS length_m,
           p.solar_mean AS solar, p.lst_summer_c AS lst_c, p.daily_cyclists_summer AS riders_summer,
           ST_AsGeoJSON(p.geom, 2) AS utm,
           ST_AsGeoJSON(ST_Transform(p.geom, 4326), 6) AS wgs,
           ST_AsGeoJSON(ST_LineInterpolatePoint(p.geom, 0.5), 2) AS mid_utm,
           ST_AsGeoJSON(ST_Transform(ST_LineInterpolatePoint(p.geom, 0.5), 4326), 6) AS mid_wgs,
           (SELECT min(ST_Distance(p.geom, f.geom)) FROM fountain f) AS fountain_dist_m
    FROM piece p
    ORDER BY p.segment_id, p.k
"""

_TRAIL_LINE = f"""
    {_TRAIL_LINK},
    trail_line AS (
        SELECT l.trail_id, ST_Collect(s.geom) AS geom
        FROM trail_link l JOIN cycle_segment s ON s.id = l.segment_id
        GROUP BY l.trail_id
    )
"""

_NODES_SQL = """
    SELECT sp.id, sp.syn_segment_id AS trail_id, sp.name, sp.notes,
           'junction' AS kind,
           sp.traffic_light_wait_s AS wait_s, sp.shade_pct, sp.temp_anomaly_c
    FROM syn_point sp
    WHERE sp.category = :junction_category
    ORDER BY sp.id
"""

# Where a junction goes: one query per anchor type (see config/point_anchors.yaml).
# Each returns the placed point (EWKT) and its gap to the anchor or the trail.
_PLACE_SQL = {
    "cross": f"""
        WITH {_TRAIL_LINE}
        SELECT ST_AsEWKT(ST_ClosestPoint(a.geom, b.geom)) AS placed, ST_Distance(a.geom, b.geom) AS gap_m
        FROM trail_line a, trail_line b WHERE a.trail_id = :trail AND b.trail_id = :other
    """,
    "facility": f"""
        WITH {_TRAIL_LINE}
        SELECT ST_AsEWKT(ST_ClosestPoint(a.geom, f.geom)) AS placed, ST_Distance(a.geom, f.geom) AS gap_m
        FROM trail_line a, city_facility f
        WHERE a.trail_id = :trail AND f.name = :name AND f.category = :category
        ORDER BY gap_m LIMIT 1
    """,
    "synthetic": f"""
        WITH {_TRAIL_LINE}
        SELECT ST_AsEWKT(ST_ClosestPoint(a.geom, sp.geom)) AS placed, ST_Distance(a.geom, sp.geom) AS gap_m
        FROM trail_line a, syn_point sp WHERE a.trail_id = :trail AND sp.id = :point
    """,
}

# Attributes at a placed point: fountain distance, and street + solar index of the nearest built segment.
_NODE_ATTRS_SQL = """
    WITH placed AS (SELECT ST_GeomFromEWKT(:placed) AS g),
    fountain AS (
        SELECT geom FROM drinking_fountain
        WHERE coalesce(trim(location_name), '') <> ALL(:excluded_fountains)
    )
    SELECT ST_AsGeoJSON(placed.g, 2) AS utm,
           ST_AsGeoJSON(ST_Transform(placed.g, 4326), 6) AS wgs,
           (SELECT min(ST_Distance(placed.g, f.geom)) FROM fountain f) AS fountain_dist_m,
           (SELECT ST_Distance(placed.g, sp.geom) FROM syn_point sp WHERE sp.id = :point) AS moved_m,
           near.street_name, near.solar_mean AS solar, near.id AS segment_id
    FROM placed
    CROSS JOIN LATERAL (
        SELECT s.street_name, m.solar_mean, s.id FROM cycle_segment s
        JOIN segment_metrics m ON m.segment_id = s.id
        WHERE s.cycle_class <> ALL(:excluded_classes) AND m.solar_mean IS NOT NULL
        ORDER BY ST_Distance(s.geom, placed.g), s.id
        LIMIT 1
    ) near
"""

# Real AMBici stations at their own location. The nearest (clipped) trail piece gives the trail, whose
# riders the station is capped at; the nearest built street segment gives the solar index and surface temperature.
_STATIONS_SQL = f"""
    WITH {_TRAIL_SEGMENTS}
    SELECT a.station_num, a.name, a.address, a.bike_racks,
           ST_AsGeoJSON(a.geom, 2) AS utm,
           ST_AsGeoJSON(ST_Transform(a.geom, 4326), 6) AS wgs,
           (SELECT min(ST_Distance(a.geom, f.geom)) FROM fountain f) AS fountain_dist_m,
           trail.trail_id, trail.dist AS trail_dist_m,
           street.id AS solar_segment_id, street.street_name, street.solar_mean AS solar, street.lst_summer_c AS lst_c
    FROM ambici_station a
    CROSS JOIN LATERAL (
        SELECT p.trail_id, ST_Distance(p.geom, a.geom) AS dist FROM piece p
        ORDER BY ST_Distance(p.geom, a.geom), p.segment_id, p.k
        LIMIT 1
    ) trail
    CROSS JOIN LATERAL (
        SELECT s.id, s.street_name, m.solar_mean, m.lst_summer_c FROM cycle_segment s
        JOIN segment_metrics m ON m.segment_id = s.id
        WHERE s.cycle_class <> ALL(:excluded_classes) AND m.solar_mean IS NOT NULL
        ORDER BY ST_Distance(s.geom, a.geom), s.id
        LIMIT 1
    ) street
    ORDER BY a.station_num
"""

# Synthetic data of the VAS-R1 stations that are matched to real ones.
_VAS_STATIONS_SQL = """
    SELECT id, shade_pct, temp_anomaly_c, notes FROM syn_point WHERE id = ANY(:vas_station_ids)
"""

_TRAILS_SQL = f"""
    WITH {_TRAIL_LINK}
    SELECT t.id, t.name, t.cycleway_type, t.length_m AS synthetic_length_m, t.utci_2pm_c,
           t.summer_surface_temp_c AS surface_temp_c, t.shade_2pm_pct,
           t.daily_cyclists_spring AS riders_spring, t.daily_cyclists_summer AS riders_summer,
           t.ridership_drop_pct,
           t.nearest_shelter_id, shelter.name AS nearest_shelter_name, t.thermal_risk_level AS risk_level,
           array_agg(DISTINCT s.street_name ORDER BY s.street_name) AS streets
    FROM syn_segment t
    JOIN trail_link l ON l.trail_id = t.id
    JOIN cycle_segment s ON s.id = l.segment_id
    LEFT JOIN syn_point shelter ON shelter.id = t.nearest_shelter_id
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

_PARKS_SQL = """
    SELECT id, name, round(ST_Area(geom)) AS area_m2,
           ST_AsGeoJSON(ST_Transform(ST_SimplifyPreserveTopology(geom, 1.0), 4326), 6) AS geometry
    FROM osm_park
    ORDER BY id
"""

_BIKE_PARKING_SQL = """
    SELECT id, name, address, ST_AsGeoJSON(ST_Transform(geom, 4326), 6) AS wgs
    FROM city_facility
    WHERE category = :bike_parking_category AND subcategory = :bike_parking_subcategory
    ORDER BY id
"""

_SURFACE_TEMP_SQL = f"""
    WITH {_TRAIL_LINK}
    SELECT s.id, s.street_name, m.lst_summer_c AS lst_c,
           EXISTS (SELECT 1 FROM trail_link l WHERE l.segment_id = s.id) AS on_trail,
           ST_AsGeoJSON(ST_Transform(ST_SimplifyPreserveTopology(s.geom, 1.0), 4326), 6) AS geometry
    FROM cycle_segment s JOIN segment_metrics m ON m.segment_id = s.id
    WHERE s.cycle_class <> ALL(:excluded_classes) AND m.lst_summer_c IS NOT NULL
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

# Sun-score anchors: percentiles of the solar index over every built segment of the network.
_SOLAR_ANCHORS_SQL = """
    SELECT percentile_cont(:lo) WITHIN GROUP (ORDER BY m.solar_mean) AS lo,
           percentile_cont(:hi) WITHIN GROUP (ORDER BY m.solar_mean) AS hi
    FROM segment_metrics m JOIN cycle_segment s ON s.id = m.segment_id
    WHERE s.cycle_class <> ALL(:excluded_classes) AND m.solar_mean IS NOT NULL
"""

_WEATHER_SQL = """
    SELECT time, temp_c, rh_pct, wind_ms, ghi_wm2, dhi_wm2, direct_h_wm2, dni_wm2 FROM weather_hour ORDER BY time
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
        segment_id=rec.get("segment_id"),
        lst_c=None if rec.get("lst_c") is None else float(rec["lst_c"]),
        riders_day=float(rec.get("riders_day", 0.0)),
        wait_s=float(rec.get("wait_s", 0.0)),
        shade_pct=float(rec.get("shade_pct", 0.0)),
        temp_anomaly_c=float(rec.get("temp_anomaly_c", 0.0)),
    )


def _rows(conn: Connection, sql: str, **extra: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(text(sql), {**_PARAMS, **extra}).mappings()]


def _vas_station_matches(assumptions: dict[str, Any]) -> dict[int, str]:
    """{real AMBici station number: VAS-R1 station id}, from entries like "EST-B01 → 34863"."""
    matches = {}
    for entry in assumptions["vas_station_match"]:
        vas_id, station_num = (part.strip() for part in entry.split("→"))
        matches[int(station_num)] = vas_id
    return matches


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ---------------------------------------------------------------- loaders
def _load_pieces(conn: Connection) -> list[dict[str, Any]]:
    pieces = []
    for r in _rows(conn, _PIECES_SQL):
        pieces.append(
            {
                "id": _piece_id(r["segment_id"], r["k"], r["n"]),
                "kind": "segment",
                "trail_id": r["trail_id"],
                "segment_id": str(r["segment_id"]),
                "street": r["street_name"],
                "cycle_class": r["cycle_class"],
                "length_m": _num(r["length_m"], 2),
                "solar": _num(r["solar"], 1),
                "lst_c": None if r["lst_c"] is None else _num(r["lst_c"], 2),
                "riders_summer": None if r["riders_summer"] is None else _num(r["riders_summer"]),
                "utm": _coords(r["utm"]),
                "mid_utm": _coords(r["mid_utm"])[0],
                "wgs": _latlon(r["wgs"]),
                "mid_wgs": _latlon(r["mid_wgs"])[0],
                "fountain_dist_m": _num(r["fountain_dist_m"], 1),
            }
        )
    return pieces


def _place(conn: Connection, node: dict[str, Any], anchors: dict[str, Any]) -> tuple[str, str]:
    """Placed point (EWKT) of a junction and a sentence saying how it was placed."""
    trail = node["trail_id"]
    anchor = anchors.get(node["id"]) or {}
    if "cross" in anchor:
        other = anchor["cross"]
        rows = _rows(conn, _PLACE_SQL["cross"], trail=trail, other=other)
        if rows:
            gap = rows[0]["gap_m"]
            how = (
                f"Crossing of {trail} and {other}" if gap < 1
                else f"Point of {trail} closest to {other} (they don't meet; {gap:.0f} m apart)"
            )
            return rows[0]["placed"], how
    elif "facility" in anchor:
        fac = anchor["facility"]
        rows = _rows(conn, _PLACE_SQL["facility"], trail=trail, name=fac["name"], category=fac["category"])
        if rows:
            return rows[0]["placed"], f"Point of {trail} closest to {fac['name']} (municipal facility, {rows[0]['gap_m']:.0f} m away)"
    rows = _rows(conn, _PLACE_SQL["synthetic"], trail=trail, point=node["id"])
    return rows[0]["placed"], f"Synthetic coordinate snapped onto {trail} (approximate)"


def _load_nodes(conn: Connection, anchors: dict[str, Any]) -> list[dict[str, Any]]:
    points = []
    for node in _rows(conn, _NODES_SQL):
        placed, how = _place(conn, node, anchors)
        r = _rows(conn, _NODE_ATTRS_SQL, placed=placed, point=node["id"])[0]
        utm, wgs = _coords(r["utm"]), _latlon(r["wgs"])
        points.append(
            {
                "id": node["id"],
                "kind": node["kind"],
                "trail_id": node["trail_id"],
                "street": r["street_name"],
                "name": node["name"],
                "notes": node["notes"],
                "length_m": 0.0,
                "solar": _num(r["solar"], 1),  # real solar index of the nearest built segment
                "solar_from": str(r["segment_id"]),
                "wait_s": _num(node["wait_s"]),
                "shade_pct": _num(node["shade_pct"]),
                "temp_anomaly_c": _num(node["temp_anomaly_c"]),
                "utm": utm,
                "mid_utm": utm[0],
                "wgs": wgs,
                "mid_wgs": wgs[0],
                "located_by": how,
                "snap_distance_m": _num(r["moved_m"], 1),  # distance from the synthetic coordinate
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
            "trail_id": r["trail_id"],  # nearest trail: the station's users are capped at its riders
            "street": r["street_name"],
            "name": r["name"],
            "address": r["address"],
            "bike_racks": r["bike_racks"],
            "length_m": 0.0,
            "solar": _num(r["solar"], 1),  # real solar index of the nearest street segment
            "solar_from": str(r["solar_segment_id"]),
            "lst_c": None if r["lst_c"] is None else _num(r["lst_c"], 2),  # same segment's surface temperature
            "utm": utm,
            "mid_utm": utm[0],
            "wgs": wgs,
            "mid_wgs": wgs[0],
            "located_by": f"Real AMBici station ({r['trail_dist_m']:.0f} m from {r['trail_id']})",
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
        real_len = sum(p["length_m"] for p in points if p["kind"] == "segment" and p["trail_id"] == r["id"])
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
                "riders_spring": _num(r["riders_spring"]),
                "riders_summer": _num(r["riders_summer"]),
                "ridership_drop_pct": _num(r["ridership_drop_pct"]),
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


def _load_parks(conn: Connection) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": r["id"], "name": r["name"], "area_m2": _num(r["area_m2"])},
                "geometry": json.loads(r["geometry"]),
            }
            for r in _rows(conn, _PARKS_SQL)
        ],
    }


def _load_bike_parkings(conn: Connection) -> list[dict[str, Any]]:
    return [
        {"id": f"BP-{r['id']}", "name": r["name"], "address": r["address"], "wgs": _latlon(r["wgs"])[0]}
        for r in _rows(conn, _BIKE_PARKING_SQL)
    ]


def _load_surface_temp(conn: Connection) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": r["id"], "street": r["street_name"], "lst_c": _num(r["lst_c"]), "on_trail": bool(r["on_trail"]),
                },
                "geometry": json.loads(r["geometry"]),
            }
            for r in _rows(conn, _SURFACE_TEMP_SQL)
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
    if not any(p["kind"] == "segment" and p["trail_id"] is not None for p in points):
        problems.append("no trail segments")
    if not any(p["kind"] == "station" for p in points):
        problems.append("no AMBici stations")
    unmatched = sorted(set(matches.values()) - {p.get("vas_id") for p in points})
    if unmatched:
        problems.append(f"VAS-R1 stations without their real AMBici station: {', '.join(unmatched)}")
    missing = sorted({*CATALOGUE_IDS, MODAL_SHIFT_ID} - set(catalogue))
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


def _heat(
    points: list[MapPoint], trails: dict[str, Trail], solar_min: float, solar_max: float,
    weather: DesignWeather, assumptions: dict[str, Any],
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    """Baseline UTCI per point and the inputs it was computed from.

    Pieces and stations: computed by heat_model from the design weather, the share of direct sun (the sun
    score of the real solar index: its network 5th percentile is full shade, the 95th full sun) and the
    ground temperature (Landsat; the network median where a segment has none).
    Junctions: the synthetic VAS-R1 value, trail UTCI plus the junction's local anomaly.
    """
    lst_known = sorted(p.lst_c for p in points if p.lst_c is not None)
    lst_fallback = lst_known[len(lst_known) // 2] if lst_known else weather.temp_c
    albedo = float(assumptions["ground_albedo"])
    emissivity = float(assumptions["ground_emissivity"])

    base: dict[str, float] = {}
    inputs: dict[str, dict[str, Any]] = {}
    for p in points:
        if p.kind == "junction":
            utci = trails[p.trail_id].utci + p.temp_anomaly_c
            base[p.id] = round(utci, 3)
            inputs[p.id] = {"utci_source": "synthetic"}
            continue
        sun_share = clamp01((p.solar - solar_min) / (solar_max - solar_min))
        heat = place_heat(weather, sun_share, p.lst_c if p.lst_c is not None else lst_fallback, albedo, emissivity)
        base[p.id] = heat["utci_c"]
        inputs[p.id] = {**heat, "utci_source": "computed"}
    return base, inputs


def load_dataset() -> Dataset:
    assumption_list = yaml.safe_load(ASSUMPTIONS_FILE.read_text(encoding="utf-8"))
    assumptions = {a["key"]: a["value"] for a in assumption_list}
    anchors = yaml.safe_load(ANCHORS_FILE.read_text(encoding="utf-8")) or {}
    matches = _vas_station_matches(assumptions)
    with engine.connect() as conn:
        pieces = _load_pieces(conn)
        points_raw = pieces + _load_nodes(conn, anchors) + _load_stations(conn, matches)
        trails_raw = _load_trails(conn, points_raw)
        fountains = _load_fountains(conn)
        parks = _load_parks(conn)
        bike_parkings = _load_bike_parkings(conn)
        surface_temp = _load_surface_temp(conn)
        catalogue = _load_catalogue(conn)
        solar = _rows(
            conn, _SOLAR_ANCHORS_SQL,
            lo=float(assumptions["solar_low_pct"]) / 100, hi=float(assumptions["solar_high_pct"]) / 100,
        )[0]
        weather_rows = _rows(conn, _WEATHER_SQL)
    _check(trails_raw, points_raw, catalogue, matches)
    if not weather_rows:
        raise RuntimeError("weather_hour is empty. Run: python scripts/export_to_db.py")
    weather = design_weather(
        weather_rows,
        hour=int(assumptions["heat_reference_hour"]),
        hot_pct=float(assumptions["hot_day_percentile"]),
        overpass_hours=[int(h) for h in assumptions["landsat_overpass_hours"]],
    )

    # Riders on a piece: its trail's spring riders; off the trails, the segment's assumed summer riders
    # (class median of the matched streets, from the seed) scaled by the trails' spring / summer ratio.
    trails = {t["id"]: Trail(id=t["id"], raw=t) for t in trails_raw}
    summer = sum(t.riders_summer for t in trails.values())
    spring_ratio = sum(t.riders_spring for t in trails.values()) / summer if summer > 0 else 1.0
    for r in points_raw:
        if r["kind"] != "segment":
            continue
        if r["trail_id"] is not None:
            r["riders_day"] = trails[r["trail_id"]].riders_spring
        else:
            r["riders_day"] = round((r["riders_summer"] or 0.0) * spring_ratio, 1)

    points = [_to_point(r) for r in points_raw]
    solar_min, solar_max = float(solar["lo"]), float(solar["hi"])
    base_utci, heat_inputs = _heat(points, trails, solar_min, solar_max, weather, assumptions)
    for r in points_raw:
        r["utci_base_c"] = base_utci[r["id"]]
        r.update(heat_inputs[r["id"]])

    pieces_by_segment: dict[str, list[MapPoint]] = {}
    for p in points:
        if p.segment_id is not None:
            pieces_by_segment.setdefault(p.segment_id, []).append(p)

    return Dataset(
        points=points,
        points_by_id={p.id: p for p in points},
        pieces_by_segment=pieces_by_segment,
        trails=trails,
        fountains=fountains,
        catalogue={k: v for k, v in catalogue.items() if k != MODAL_SHIFT_ID},
        modal_shift=catalogue[MODAL_SHIFT_ID],
        assumptions=assumptions,
        assumption_list=assumption_list,
        parks=parks,
        bike_parkings=bike_parkings,
        surface_temp=surface_temp,
        solar_min=solar_min,
        solar_max=solar_max,
        weather=weather,
        off_trail_spring_ratio=spring_ratio,
        base_utci=base_utci,
    )


@lru_cache(maxsize=1)
def get_dataset() -> Dataset:
    return load_dataset()
