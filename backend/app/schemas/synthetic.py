"""Synthetic VAS-R1 challenge data. Must be labelled as synthetic/demo data in the UI."""

from typing import Literal

from pydantic import Field

from app.schemas.network import OrmModel

UnitKind = Literal["per_100m", "per_site", "city_wide", "reference"]
AppliesTo = Literal["segment", "junction", "station", "network"]
MatchMethod = Literal["street_name", "manual"]


class InterventionType(OrmModel):
    id: str = Field(examples=["INT-01"])
    source_id: int
    category: str
    description: str
    unit_label: str
    unit_kind: UnitKind
    applies_to: AppliesTo
    capex_eur: int = Field(ge=0)
    opex_eur_yr: int = Field(ge=0)
    surface_temp_reduction_c: float | None = None
    utci_improvement_c: float | None = None
    co2_kg_yr: float | None = None
    deployment_weeks: int | None = None
    notes: str | None = None


class HourlyProfile(OrmModel):
    hour: int = Field(ge=0, le=23)
    source_id: int
    air_temp_c: float
    rel_humidity_pct: int | None = None
    solar_radiation_wm2: int | None = None
    utci_unshaded_asphalt_c: float | None = None
    utci_building_shaded_c: float | None = None
    utci_shaded_park_c: float | None = None
    utci_cool_lane_c: float | None = None
    cyclist_flow_spring: int | None = None
    cyclist_flow_summer: int | None = None


class SynSegment(OrmModel):
    id: str = Field(examples=["TRM-01"])
    source_id: int
    name: str
    cycleway_type: str | None = None
    length_m: int | None = None
    shade_10am_pct: float | None = None
    shade_2pm_pct: float | None = None
    shade_6pm_pct: float | None = None
    pavement_surface: str | None = None
    summer_surface_temp_c: float | None = None
    utci_2pm_c: float | None = None
    daily_cyclists_spring: int | None = None
    daily_cyclists_summer: int | None = None
    ridership_drop_pct: float | None = None


class SynSegmentLink(OrmModel):
    syn_segment_id: str
    segment_id: int
    match_method: MatchMethod
