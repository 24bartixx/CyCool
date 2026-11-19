from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from geoalchemy2 import WKBElement
from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, line_geometry

if TYPE_CHECKING:
    from app.models.data_source import DataSource
    from app.models.segment_metrics import SegmentMetrics
    from app.models.syn_segment_link import SynSegmentLink


class CycleSegment(Base):
    """Municipal cycle network section (real geometry)."""

    __tablename__ = "cycle_segment"
    __table_args__ = (
        CheckConstraint("length_m > 0", name="cycle_segment_length_m_check"),
        Index("cycle_segment_geom_idx", "geom", postgresql_using="gist"),
        Index("cycle_segment_street_idx", "street_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # source objectid
    globalid: Mapped[UUID] = mapped_column(unique=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_source.id"))
    idf: Mapped[int | None]
    codvia: Mapped[str | None] = mapped_column(Text)
    street_name: Mapped[str] = mapped_column(Text)
    cycle_class: Mapped[str] = mapped_column(Text)  # raw source value, incl. 'NO' and '0'
    is_cycle_candidate: Mapped[bool]
    length_m: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    geom: Mapped[WKBElement] = mapped_column(line_geometry())

    source: Mapped[DataSource] = relationship()
    metrics: Mapped[SegmentMetrics | None] = relationship(back_populates="segment", uselist=False, passive_deletes=True)
    syn_links: Mapped[list[SynSegmentLink]] = relationship(back_populates="segment", passive_deletes=True)
