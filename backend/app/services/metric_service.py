"""Scores (0 = fine, 1 = worst) and priority for every trail point."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.dataset import Dataset, MapPoint
from app.services.effect_service import PointState

METRICS = ("water", "sun", "heat", "combined")


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass(frozen=True)
class Scores:
    water: float
    sun: float
    heat: float

    @property
    def combined(self) -> float:
        return (self.water + self.sun + self.heat) / 3

    def get(self, metric: str) -> float:
        return self.combined if metric == "combined" else getattr(self, metric)

    def as_dict(self) -> dict[str, float]:
        return {"water": self.water, "sun": self.sun, "heat": self.heat, "combined": self.combined}


def solar_score(ds: Dataset, solar: float) -> float:
    return clamp01((solar - ds.solar_min) / (ds.solar_max - ds.solar_min))


def wait_exposure(ds: Dataset, s: PointState) -> float:
    """Share of a full-sun wait at the red light: (wait / reference) x unshaded share."""
    return clamp01(s.wait_s / float(ds.assumptions["junction_wait_ref_s"])) * (1 - s.shade_pct / 100)


def score_point(ds: Dataset, p: MapPoint, s: PointState) -> Scores:
    a = ds.assumptions
    water = clamp01((s.water_dist_m - a["water_ok_m"]) / (a["water_bad_m"] - a["water_ok_m"]))
    sun = solar_score(ds, s.solar)
    if p.kind == "junction":
        sun = (sun + wait_exposure(ds, s)) / 2
    heat = clamp01((s.utci - a["utci_ok_c"]) / (a["utci_bad_c"] - a["utci_ok_c"]))
    return Scores(water=water, sun=sun, heat=heat)


def weight_m(ds: Dataset, p: MapPoint) -> float:
    return p.length_m if p.kind == "segment" else float(ds.assumptions["point_weight_m"])


def priority(ds: Dataset, p: MapPoint, score: float) -> float:
    """score x (length or point weight) / 100 m."""
    return score * weight_m(ds, p) / 100


def score_all(ds: Dataset, state: dict[str, PointState]) -> dict[str, Scores]:
    return {p.id: score_point(ds, p, state[p.id]) for p in ds.points}


def total_priority(ds: Dataset, scores: dict[str, Scores], metric: str) -> float:
    return sum(priority(ds, p, scores[p.id].get(metric)) for p in ds.points)
