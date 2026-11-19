from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from geoalchemy2 import WKBElement
from sqlalchemy import ForeignKey, Index, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, point_geometry

if TYPE_CHECKING:
    from app.models.data_source import DataSource
    from app.models.syn_segment import SynSegment


class SynPoint(Base):
    """Synthetic VAS-R1 point: traffic-light junction (CRU-*), climate shelter (REF-*) or bike station (EST-*).

    The coordinates are the synthetic ones (140-850 m off the real streets); the backend snaps
    junctions and stations onto their linked trail when it loads the dataset.
    """

    __tablename__ = "syn_point"
    __table_args__ = (Index("syn_point_geom_idx", "geom", postgresql_using="gist"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # CRU-01, REF-01, EST-B01, ...
    source_id: Mapped[int] = mapped_column(ForeignKey("data_source.id"))
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    syn_segment_id: Mapped[str] = mapped_column(Text, ForeignKey("syn_segment.id"))
    traffic_light_wait_s: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    shade_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    temp_anomaly_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    notes: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[WKBElement] = mapped_column(point_geometry())

    source: Mapped[DataSource] = relationship()
    syn_segment: Mapped[SynSegment] = relationship()
