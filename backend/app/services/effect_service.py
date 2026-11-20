"""Fix rules, plan validation and how each accepted fix changes the state of the trail points.

All effect sizes come from the catalogue (UTCI reduction, cost, CO2) or from assumptions.yaml. Each fix acts
through its physical mechanism: shade and cooling lower UTCI/sun, the green wave shortens the red-light
wait (time in the heat), the oasis adds a water and rest stop.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.services.dataset import Dataset, MapPoint

# Where each catalogue fix may be placed and whether it is laid along a street (priced per linear metre).
FIX_RULES: dict[str, dict] = {
    "INT-01": {"label": "Shade trees", "kinds": {"segment"}, "linear": True},
    "INT-02": {"label": "Shade sail at waiting box", "kinds": {"junction"}, "linear": False},
    "INT-03": {"label": "Cyclist oasis", "kinds": {"segment", "station"}, "linear": False},
    "INT-04": {"label": "Cool pavement", "kinds": {"segment"}, "linear": True},
    # Offered only under the combined metric: it shortens the wait, which only the combined score counts.
    "INT-05": {"label": "Green-wave traffic lights", "kinds": {"junction"}, "linear": False, "metrics": {"combined"}},
    "INT-06": {"label": "Station solar canopy", "kinds": {"station"}, "linear": False},
}


def offered(fix_id: str, metric: str) -> bool:
    """Whether a fix is offered (recommended, auto-planned) under the selected metric. A fix already in the
    plan stays valid under every metric; this only controls what can be picked."""
    allowed = FIX_RULES[fix_id].get("metrics")
    return allowed is None or metric in allowed


class PlanError(ValueError):
    """Raised when a plan (list of accepted fixes) is invalid."""


@dataclass(frozen=True)
class PointState:
    utci: float
    solar: float
    wait_s: float
    shade_pct: float
    water_dist_m: float
    utci_base: float = 0.0
    utci_cuts: tuple[float, ...] = ()  # UTCI reductions of the fixes here (positive °C)


@dataclass(frozen=True)
class AppliedFix:
    fix_id: str
    point_id: str
    cost_eur: float
    opex_eur_yr: float
    co2_kg_yr: float
    length_m: float  # street length the fix is laid along (0 for point fixes)


def targets(ds: Dataset, fix_id: str, point: MapPoint) -> list[MapPoint]:
    """Points a fix is applied to: the whole real segment for linear fixes, the point itself otherwise."""
    if FIX_RULES[fix_id]["linear"] and point.segment_id is not None:
        return ds.pieces_by_segment[point.segment_id]
    return [point]


def target_key(ds: Dataset, fix_id: str, point: MapPoint) -> str:
    """Identity of the place a fix occupies, so the same street segment can't get trees twice."""
    if FIX_RULES[fix_id]["linear"] and point.segment_id is not None:
        return f"segment:{point.segment_id}"
    return f"point:{point.id}"


def fix_length_m(ds: Dataset, fix_id: str, point: MapPoint) -> float:
    if not FIX_RULES[fix_id]["linear"]:
        return 0.0
    return sum(p.length_m for p in targets(ds, fix_id, point))


def linear_share(ds: Dataset, fix_id: str, point: MapPoint) -> float:
    """Share of the catalogue unit used: segment length / 100 m for linear fixes, 1 otherwise."""
    if FIX_RULES[fix_id]["linear"]:
        return fix_length_m(ds, fix_id, point) / float(ds.assumptions["linear_fix_unit_m"])
    return 1.0


def describe_fix(ds: Dataset, fix_id: str, point: MapPoint) -> AppliedFix:
    share = linear_share(ds, fix_id, point)
    cat = ds.catalogue[fix_id]
    return AppliedFix(
        fix_id=fix_id,
        point_id=point.id,
        cost_eur=round(cat["capex_eur"] * share, 2),
        opex_eur_yr=round(cat["opex_eur_yr"] * share, 2),
        co2_kg_yr=round(cat["co2_kg_yr"] * share, 3),
        length_m=round(fix_length_m(ds, fix_id, point), 1),
    )


def fix_cost(ds: Dataset, fix_id: str, point: MapPoint) -> float:
    return describe_fix(ds, fix_id, point).cost_eur


def baseline_state(ds: Dataset) -> dict[str, PointState]:
    state = {}
    for p in ds.points:
        utci = ds.base_utci[p.id]
        state[p.id] = PointState(
            utci=utci, solar=p.solar, wait_s=p.wait_s, shade_pct=p.shade_pct,
            water_dist_m=p.fountain_dist_m, utci_base=utci,
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
        key = (fix_id, target_key(ds, fix_id, point))
        if key in seen:
            where = "this street segment" if FIX_RULES[fix_id]["linear"] else point_id
            raise PlanError(f"{fix_id} is already applied at {where}.")
        seen.add(key)
        priced = describe_fix(ds, fix_id, point)
        spent += priced.cost_eur
        if spent > budget + 0.005:
            raise PlanError(f"Adding {fix_id} at {point_id} exceeds the budget.")
        applied.append(priced)
    return applied


def _cool(ds: Dataset, s: PointState, cut_c: float) -> PointState:
    """Adds one UTCI reduction. The largest counts fully, the others at the stacking factor."""
    cuts = (*s.utci_cuts, abs(cut_c))
    biggest = max(cuts)
    total = biggest + float(ds.assumptions["stacking_secondary_factor"]) * (sum(cuts) - biggest)
    return replace(s, utci_cuts=cuts, utci=s.utci_base - total)


def apply_fix(ds: Dataset, state: dict[str, PointState], fix_id: str, point: MapPoint) -> dict[str, PointState]:
    """Returns a new state with one fix applied (the input state is not modified)."""
    a = ds.assumptions
    cut = float(ds.catalogue[fix_id]["utci_reduction_c"])  # negative number in the catalogue
    new = dict(state)
    if fix_id in ("INT-01", "INT-04"):
        for q in targets(ds, fix_id, point):
            s = _cool(ds, new[q.id], cut)
            if fix_id == "INT-01":
                s = replace(s, solar=s.solar * (1 - a["trees_solar_cut"]))
            new[q.id] = s
    elif fix_id == "INT-02":
        new[point.id] = replace(_cool(ds, new[point.id], cut), shade_pct=100.0)
    elif fix_id == "INT-05":
        # Shorter wait at the red light, same temperature there: it counts through the exposure time.
        s = new[point.id]
        new[point.id] = replace(s, wait_s=min(s.wait_s, float(a["green_wave_wait_s"])))
    elif fix_id == "INT-06":
        s = _cool(ds, new[point.id], cut)
        new[point.id] = replace(s, solar=s.solar * (1 - a["canopy_solar_cut"]))
    elif fix_id == "INT-03":
        # A rest and water stop beside the route. Water reaches every point nearby. Its pergola and mist
        # cool the people who stop at the oasis itself, not riders passing by or waiting in a traffic-light
        # box, so it changes no UTCI or sun on the network.
        oasis = point.mid
        for q in ds.points:
            dist = q.geom.distance(oasis)
            if dist < new[q.id].water_dist_m:
                new[q.id] = replace(new[q.id], water_dist_m=dist)
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
        return [utci, f"sun −{a['trees_solar_cut']:.0%}", "whole street segment", f"{cat['co2_kg_yr']:.0f} kg CO₂/yr per 100 m"]
    if fix_id == "INT-04":
        return [utci, f"surface {cat['surface_temp_reduction_c']:+.1f} °C", "whole street segment"]
    if fix_id == "INT-02":
        return [utci, "waiting box fully shaded"]
    if fix_id == "INT-05":
        return [f"red-light wait ≤ {a['green_wave_wait_s']} s", "less time in the heat, same temperature", "lowers the combined score"]
    if fix_id == "INT-06":
        return [utci, f"sun −{a['canopy_solar_cut']:.0%}", f"{cat['co2_kg_yr']:.0f} kg CO₂/yr"]
    if fix_id == "INT-03":
        return [
            "adds drinking water and a rest stop",
            f"{utci} only for people who stop at the oasis",
            "no cooling for riders passing or waiting at a red light",
        ]
    return [utci]
