from __future__ import annotations

from typing import TYPE_CHECKING

from geoalchemy2 import WKBElement
from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, point_geometry

if TYPE_CHECKING:
    from app.models.data_source import DataSource


class CityFacility(Base):
    """General municipal facility; not automatically a climate shelter."""

    __tablename__ = "city_facility"
    __table_args__ = (Index("city_facility_geom_idx", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # source fid
    source_id: Mapped[int] = mapped_column(ForeignKey("data_source.id"))
    name: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    subcategory: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[WKBElement] = mapped_column(point_geometry())

    source: Mapped[DataSource] = relationship()
