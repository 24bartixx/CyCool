"""Loads the pre-built prototype dataset (see scripts/build_dataset.py) once per process."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
ASSUMPTIONS_FILE = APP_DIR / "config" / "assumptions.yaml"


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

    @property
    def riders_spring(self) -> int:
        return int(self.raw["riders_spring"])

    @property
    def riders_summer(self) -> int:
        return int(self.raw["riders_summer"])

    @property
    def synthetic_length_km(self) -> float:
        return float(self.raw["synthetic_length_m"]) / 1000


@dataclass(frozen=True)
class Dataset:
    points: list[MapPoint]
    points_by_id: dict[str, MapPoint]
    trails: dict[str, Trail]
    fountains: list[dict[str, Any]]
    catalogue: dict[str, dict[str, Any]]
    modal_reference: dict[str, Any]
    assumptions: dict[str, Any]
    assumption_list: list[dict[str, Any]]
    context_network: dict[str, Any]
    solar_min: float
    solar_max: float


def _read_json(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


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


def load_dataset() -> Dataset:
    points = [_to_point(r) for r in _read_json("points.json")]
    trails = {t["id"]: Trail(id=t["id"], raw=t) for t in _read_json("trails.json")}
    catalogue_file = _read_json("catalogue.json")
    assumption_list = yaml.safe_load(ASSUMPTIONS_FILE.read_text(encoding="utf-8"))
    segment_solar = [p.solar for p in points if p.kind == "segment"]
    return Dataset(
        points=points,
        points_by_id={p.id: p for p in points},
        trails=trails,
        fountains=_read_json("fountains.json"),
        catalogue={c["id"]: c for c in catalogue_file["interventions"]},
        modal_reference=catalogue_file["modal_shift_reference"],
        assumptions={a["key"]: a["value"] for a in assumption_list},
        assumption_list=assumption_list,
        context_network=_read_json("context_network.geojson"),
        solar_min=min(segment_solar),
        solar_max=max(segment_solar),
    )


@lru_cache(maxsize=1)
def get_dataset() -> Dataset:
    return load_dataset()
