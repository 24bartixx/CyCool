"""Scores (0 = fine, 1 = worst), ranking and burden for every trail point.

- severity (ranks the worst list) = score x riders/day at the point. It does not depend on how long a
  trail piece happens to be, so cutting the network differently doesn't reorder the list.
- burden (what a plan reduces) = score x riders/day x seconds a rider spends there, in rider-hours.
  Pieces: length / cycling speed, scaled so a trail's total ride time matches its VAS-R1 length;
  junctions: their red-light wait (a green wave shortens it); stations: the dwell time.
  A fix counts through the score, except the green wave, which counts through the time.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.dataset import Dataset, MapPoint, clamp01
from app.services.effect_service import PointState

METRICS = ("water", "sun", "heat", "combined")


@dataclass(frozen=True)
class Scores:
    water: float
    sun: float
    heat: float
    combined: float

    def get(self, metric: str) -> float:
        return getattr(self, metric)

    def as_dict(self) -> dict[str, float]:
        return {"water": self.water, "sun": self.sun, "heat": self.heat, "combined": self.combined}


def combined_weights(ds: Dataset) -> tuple[float, float, float]:
    """(water, sun, heat) weights of the combined score, normalised to sum 1."""
    a = ds.assumptions
    w = (float(a["weight_water"]), float(a["weight_sun"]), float(a["weight_heat"]))
    total = sum(w)
    return (w[0] / total, w[1] / total, w[2] / total) if total > 0 else (1 / 3, 1 / 3, 1 / 3)


def solar_score(ds: Dataset, solar: float) -> float:
    return clamp01((solar - ds.solar_min) / (ds.solar_max - ds.solar_min))


def unshaded_share(s: PointState) -> float:
    """Share of the red-light waiting box in full sun."""
    return clamp01(1 - s.shade_pct / 100)


def score_point(ds: Dataset, p: MapPoint, s: PointState) -> Scores:
    a = ds.assumptions
    water = clamp01((s.water_dist_m - a["water_ok_m"]) / (a["water_bad_m"] - a["water_ok_m"]))
    sun = solar_score(ds, s.solar)
    if p.kind == "junction":
        # The waiting box's own shade; how long riders wait there is the exposure time of the burden.
        sun = (sun + unshaded_share(s)) / 2
    heat = clamp01((s.utci - a["utci_ok_c"]) / (a["utci_bad_c"] - a["utci_ok_c"]))
    ww, ws, wh = combined_weights(ds)
    return Scores(water=water, sun=sun, heat=heat, combined=ww * water + ws * sun + wh * heat)


def riders(ds: Dataset, p: MapPoint) -> float:
    """Riders/day at the point.

    Trail pieces and junctions: spring riders/day of the trail (the people the route serves when the heat
    doesn't keep them away). Stations: only the people who dock there, capped at the trail's riders.
    """
    trail_riders = ds.trails[p.trail_id].riders_spring
    if p.kind == "station":
        return min(trail_riders, float(ds.assumptions["station_users_per_day"]))
    return trail_riders


def exposure_s(ds: Dataset, p: MapPoint, s: PointState) -> float:
    """Seconds a rider spends at the point."""
    a = ds.assumptions
    if p.kind == "segment":
        return p.length_m * ds.trails[p.trail_id].length_scale / float(a["cycling_speed_ms"])
    if p.kind == "junction":
        return s.wait_s
    return float(a["station_dwell_s"])


def severity(ds: Dataset, p: MapPoint, score: float) -> float:
    return score * riders(ds, p)


def burden(ds: Dataset, p: MapPoint, s: PointState, score: float) -> float:
    """Score-weighted rider-hours per day at this point."""
    return score * riders(ds, p) * exposure_s(ds, p, s) / 3600


def score_all(ds: Dataset, state: dict[str, PointState]) -> dict[str, Scores]:
    return {p.id: score_point(ds, p, state[p.id]) for p in ds.points}


def total_burden(ds: Dataset, state: dict[str, PointState], scores: dict[str, Scores], metric: str) -> float:
    return sum(burden(ds, p, state[p.id], scores[p.id].get(metric)) for p in ds.points)
