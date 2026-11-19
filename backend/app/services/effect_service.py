"""Fix rules, plan validation and how each accepted fix changes the state of the trail points.

All effect sizes come from the catalogue (UTCI reduction, cost, CO2) or from assumptions.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.services.dataset import Dataset, MapPoint

# Where each catalogue fix may be placed and whether it is priced per linear metre.
FIX_RULES: dict[str, dict] = {
    "INT-01": {"label": "Shade trees", "kinds": {"segment"}, "linear": True},
    "INT-02": {"label": "Shade sail at waiting box", "kinds": {"junction"}, "linear": False},
    "INT-03": {"label": "Cyclist oasis", "kinds": {"segment", "junction", "station"}, "linear": False},
    "INT-04": {"label": "Cool pavement", "kinds": {"segment"}, "linear": True},
    "INT-05": {"label": "Green-wave traffic lights", "kinds": {"junction"}, "linear": False},
    "INT-06": {"label": "Station solar canopy", "kinds": {"station"}, "linear": False},
}

EPS = 1e-9


class PlanError(ValueError):
    """Raised when a plan (list of accepted fixes) is invalid."""


@dataclass(frozen=True)
class PointState:
    utci: float
    solar: float
    wait_s: float
    shade_pct: float
    water_dist_m: float


@dataclass(frozen=True)
class AppliedFix:
    fix_id: str
    point_id: str
    cost_eur: float
    opex_eur_yr: float
    co2_kg_yr: float


def linear_share(ds: Dataset, fix_id: str, point: MapPoint) -> float:
    """Share of the catalogue unit used: length/100 m for linear fixes, 1 otherwise."""
    if FIX_RULES[fix_id]["linear"]:
        return point.length_m / float(ds.assumptions["linear_fix_unit_m"])
    return 1.0


def fix_cost(ds: Dataset, fix_id: str, point: MapPoint) -> float:
    return round(ds.catalogue[fix_id]["capex_eur"] * linear_share(ds, fix_id, point), 2)


def describe_fix(ds: Dataset, fix_id: str, point: MapPoint) -> AppliedFix:
    share = linear_share(ds, fix_id, point)
    cat = ds.catalogue[fix_id]
    return AppliedFix(
        fix_id=fix_id,
        point_id=point.id,
        cost_eur=round(cat["capex_eur"] * share, 2),
        opex_eur_yr=round(cat["opex_eur_yr"] * share, 2),
        co2_kg_yr=round(cat["co2_kg_yr"] * share, 3),
    )


def baseline_state(ds: Dataset) -> dict[str, PointState]:
    state = {}
    for p in ds.points:
        utci = ds.trails[p.trail_id].utci + (p.temp_anomaly_c if p.kind != "segment" else 0.0)
        state[p.id] = PointState(
            utci=utci, solar=p.solar, wait_s=p.wait_s, shade_pct=p.shade_pct, water_dist_m=p.fountain_dist_m
        )
    return state


def check_allowed(ds: Dataset, fix_id: str, point_id: str) -> MapPoint:
    if fix_id not in FIX_RULES:
        raise PlanError(f"Unknown fix '{fix_id}'.")
    point = ds.points_by_id.get(point_id)
    if point is None:
        raise PlanError(f"Unknown point '{point_id}'.")
    if point.kind not in FIX_RULES[fix_id]["kinds"]:
        raise PlanError(f"{FIX_RULES[fix_id]['label']} ({fix_id}) cannot be placed on a {point.kind}.")
    return point


def validate_plan(ds: Dataset, accepted: list[tuple[str, str]], budget: float) -> list[AppliedFix]:
    """Checks every accepted (fix_id, point_id) and the running budget; returns priced fixes."""
    seen: set[tuple[str, str]] = set()
    applied: list[AppliedFix] = []
    spent = 0.0
    for fix_id, point_id in accepted:
        point = check_allowed(ds, fix_id, point_id)
        if (fix_id, point_id) in seen:
            raise PlanError(f"{fix_id} is already applied at {point_id}.")
        seen.add((fix_id, point_id))
        priced = describe_fix(ds, fix_id, point)
        spent += priced.cost_eur
        if spent > budget + 0.005:
            raise PlanError(f"Adding {fix_id} at {point_id} exceeds the budget.")
        applied.append(priced)
    return applied


def apply_fix(ds: Dataset, state: dict[str, PointState], fix_id: str, point: MapPoint) -> dict[str, PointState]:
    """Returns a new state with one fix applied (the input state is not modified)."""
    a = ds.assumptions
    utci_delta = float(ds.catalogue[fix_id]["utci_reduction_c"])  # negative number in the catalogue
    new = dict(state)
    s = new[point.id]
    if fix_id == "INT-01":
        new[point.id] = replace(s, solar=s.solar * (1 - a["trees_solar_cut"]), utci=s.utci + utci_delta)
    elif fix_id == "INT-04":
        new[point.id] = replace(s, utci=s.utci + utci_delta)
    elif fix_id == "INT-02":
        new[point.id] = replace(s, shade_pct=100.0, utci=s.utci + utci_delta)
    elif fix_id == "INT-05":
        new[point.id] = replace(s, wait_s=min(s.wait_s, float(a["green_wave_wait_s"])), utci=s.utci + utci_delta)
    elif fix_id == "INT-06":
        new[point.id] = replace(s, solar=s.solar * (1 - a["canopy_solar_cut"]), utci=s.utci + utci_delta)
    elif fix_id == "INT-03":
        oasis = point.mid
        radius = float(a["oasis_radius_m"])
        for q in ds.points:
            dist = q.geom.distance(oasis)
            qs = new[q.id]
            water = min(qs.water_dist_m, dist)
            if dist <= radius + EPS:
                new[q.id] = replace(
                    qs, water_dist_m=water, utci=qs.utci + utci_delta, solar=qs.solar * (1 - a["oasis_solar_cut"])
                )
            elif water < qs.water_dist_m:
                new[q.id] = replace(qs, water_dist_m=water)
    else:  # pragma: no cover - guarded by check_allowed
        raise PlanError(f"No effect model for {fix_id}.")
    return new


def plan_state(ds: Dataset, accepted: list[tuple[str, str]]) -> dict[str, PointState]:
    state = baseline_state(ds)
    for fix_id, point_id in accepted:
        state = apply_fix(ds, state, fix_id, ds.points_by_id[point_id])
    return state


def effect_summary(ds: Dataset, fix_id: str) -> list[str]:
    """Human-readable effects, generated from the catalogue and assumptions (no hard-coded numbers)."""
    a = ds.assumptions
    cat = ds.catalogue[fix_id]
    utci = f"UTCI {cat['utci_reduction_c']:+.1f} °C"
    if fix_id == "INT-01":
        return [utci, f"sun −{a['trees_solar_cut']:.0%}", f"{cat['co2_kg_yr']:.0f} kg CO₂/yr per 100 m"]
    if fix_id == "INT-04":
        return [utci, f"surface {cat['surface_temp_reduction_c']:+.1f} °C"]
    if fix_id == "INT-02":
        return [utci, "waiting box fully shaded"]
    if fix_id == "INT-05":
        return [utci, f"red-light wait ≤ {a['green_wave_wait_s']} s"]
    if fix_id == "INT-06":
        return [utci, f"sun −{a['canopy_solar_cut']:.0%}", f"{cat['co2_kg_yr']:.0f} kg CO₂/yr"]
    if fix_id == "INT-03":
        return [
            "adds drinking water",
            f"{utci} within {a['oasis_radius_m']} m",
            f"sun −{a['oasis_solar_cut']:.0%} within {a['oasis_radius_m']} m",
        ]
    return [utci]
