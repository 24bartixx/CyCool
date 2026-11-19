"""GeoJSON geometry models. API geometry is always WGS84 (EPSG:4326, [lon, lat]).

The database stores EPSG:25831; convert with ST_Transform(geom, 4326) before serialising.
"""

from typing import Literal

from pydantic import BaseModel

Position = tuple[float, float]


class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: Position


class LineStringGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[Position]
