from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.data_source import DataSource
    from app.models.syn_segment_link import SynSegmentLink


class SynSegment(Base):
    """Synthetic VAS-R1 route (TRM-01..14). No geometry; linked to real segments by street name."""

    __tablename__ = "syn_segment"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_source.id"))
    name: Mapped[str] = mapped_column(Text)
    cycleway_type: Mapped[str | None] = mapped_column(Text)
    length_m: Mapped[int | None]
    shade_10am_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    shade_2pm_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    shade_6pm_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    pavement_surface: Mapped[str | None] = mapped_column(Text)
    summer_surface_temp_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    utci_2pm_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    daily_cyclists_spring: Mapped[int | None]
    daily_cyclists_summer: Mapped[int | None]
    ridership_drop_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    nearest_shelter_id: Mapped[str | None] = mapped_column(Text)  # a syn_point REF-* id (no FK: loaded first)
    thermal_risk_level: Mapped[str | None] = mapped_column(Text)

    source: Mapped[DataSource] = relationship()
    links: Mapped[list[SynSegmentLink]] = relationship(back_populates="syn_segment", passive_deletes=True)
