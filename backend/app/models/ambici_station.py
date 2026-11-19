from __future__ import annotations

from typing import TYPE_CHECKING

from geoalchemy2 import WKBElement
from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, point_geometry

if TYPE_CHECKING:
    from app.models.data_source import DataSource


class AmbiciStation(Base):
    __tablename__ = "ambici_station"
    __table_args__ = (Index("ambici_station_geom_idx", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # source id_estacio
    source_id: Mapped[int] = mapped_column(ForeignKey("data_source.id"))
    station_num: Mapped[int] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    bike_racks: Mapped[int | None]
    geom: Mapped[WKBElement] = mapped_column(point_geometry())

    source: Mapped[DataSource] = relationship()
