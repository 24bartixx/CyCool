from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from geoalchemy2 import WKBElement
from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, point_geometry

if TYPE_CHECKING:
    from app.models.data_source import DataSource


class DrinkingFountain(Base):
    __tablename__ = "drinking_fountain"
    __table_args__ = (Index("drinking_fountain_geom_idx", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # source objectid
    globalid: Mapped[UUID] = mapped_column(unique=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_source.id"))
    location_name: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[WKBElement] = mapped_column(point_geometry())

    source: Mapped[DataSource] = relationship()
