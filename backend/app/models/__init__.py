"""ORM models, one class per module. Importing this package registers every table on Base.metadata."""

from app.models.ambici_station import AmbiciStation
from app.models.base import SRID, Base
from app.models.city_facility import CityFacility
from app.models.cycle_segment import CycleSegment
from app.models.data_source import DataSource
from app.models.drinking_fountain import DrinkingFountain
from app.models.hourly_profile import HourlyProfile
from app.models.intervention_type import InterventionType
from app.models.osm_park import OsmPark
from app.models.plan import Plan
from app.models.plan_item import PlanItem
from app.models.segment_metrics import SegmentMetrics
from app.models.syn_point import SynPoint
from app.models.syn_segment import SynSegment
from app.models.syn_segment_link import SynSegmentLink
from app.models.weather_hour import WeatherHour

__all__ = [
    "SRID",
    "AmbiciStation",
    "Base",
    "CityFacility",
    "CycleSegment",
    "DataSource",
    "DrinkingFountain",
    "HourlyProfile",
    "InterventionType",
    "OsmPark",
    "Plan",
    "PlanItem",
    "SegmentMetrics",
    "SynPoint",
    "SynSegment",
    "SynSegmentLink",
    "WeatherHour",
]
