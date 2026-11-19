"""Declarative base and shared column helpers for the ORM models.

The models are the single source of truth for the schema. After changing them, create a
migration with `alembic revision --autogenerate -m "..."` (from backend/) and review it.

Geometry is EPSG:25831 (metres). For API output use ST_Transform(geom, 4326) + ST_AsGeoJSON,
which is what the Pydantic models in app.schemas expect in their `geometry` field.
"""

from geoalchemy2 import Geometry
from sqlalchemy.orm import DeclarativeBase

SRID = 25831


class Base(DeclarativeBase):
    pass


def line_geometry() -> Geometry:
    """LineString column; the GiST index is declared explicitly in each model."""
    return Geometry("LINESTRING", srid=SRID, spatial_index=False)


def point_geometry() -> Geometry:
    """Point column; the GiST index is declared explicitly in each model."""
    return Geometry("POINT", srid=SRID, spatial_index=False)
