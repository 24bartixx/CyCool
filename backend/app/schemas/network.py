"""Real (municipal) layers and per-segment aggregates."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.geo import LineStringGeometry, PointGeometry

SourceOrigin = Literal["municipal", "derived", "synthetic", "external"]
SolarClass = Literal["niska", "srednia", "wysoka"]
WaterAccess = Literal["near_0_100m", "medium_100_300m", "far_over_300m"]
CyclistsSource = Literal["vas_synthetic_match", "class_median_assumed"]


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DataSource(OrmModel):
    id: int
    code: str
    origin: SourceOrigin
    name: str
    url: str | None = None
    notes: str | None = None


class SegmentMetrics(OrmModel):
    segment_id: int
    fountain_dist_m: float | None = None
    ambici_dist_m: float | None = None
    facility_dist_m: float | None = None
    fountain_within_100m: bool | None = None
    fountain_within_300m: bool | None = None
    ambici_within_300m: bool | None = None
    water_access_flag: WaterAccess | None = None
    solar_mean: float | None = Field(None, description="Unitless working measure, 10 m buffer")
    solar_median: float | None = None
    solar_max: float | None = None
    solar_valid_coverage: float | None = Field(None, ge=0, le=1)
    solar_valid_pixels: int | None = None
    solar_class: SolarClass | None = None
    daily_cyclists_summer: int | None = Field(None, description="Synthetic; see cyclists_source")
    cyclists_source: CyclistsSource | None = None


class CycleSegment(OrmModel):
    id: int
    globalid: UUID
    source_id: int
    idf: int | None = None
    codvia: str | None = None
    street_name: str
    cycle_class: str
    is_cycle_candidate: bool
    length_m: float = Field(gt=0)
    geometry: LineStringGeometry


class CycleSegmentWithMetrics(CycleSegment):
    metrics: SegmentMetrics | None = None


class DrinkingFountain(OrmModel):
    id: int
    globalid: UUID
    source_id: int
    location_name: str | None = None
    geometry: PointGeometry


class AmbiciStation(OrmModel):
    id: int
    source_id: int
    station_num: int
    name: str
    address: str | None = None
    bike_racks: int | None = None
    geometry: PointGeometry


class CityFacility(OrmModel):
    id: int
    source_id: int
    name: str | None = None
    category: str | None = None
    subcategory: str | None = None
    address: str | None = None
    website: str | None = None
    geometry: PointGeometry
