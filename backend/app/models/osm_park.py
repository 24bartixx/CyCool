from __future__ import annotations

from typing import TYPE_CHECKING

from geoalchemy2 import WKBElement
from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, multipolygon_geometry

if TYPE_CHECKING:
    from app.models.data_source import DataSource


class OsmPark(Base):
    """Park outline from OpenStreetMap (leisure=park); a display-only map layer."""

    __tablename__ = "osm_park"
    __table_args__ = (Index("osm_park_geom_idx", "geom", postgresql_using="gist"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # OSM id, e.g. "way/94254419"
    source_id: Mapped[int] = mapped_column(ForeignKey("data_source.id"))
    name: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[WKBElement] = mapped_column(multipolygon_geometry())

    source: Mapped[DataSource] = relationship()
