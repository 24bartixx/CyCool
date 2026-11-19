from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.cycle_segment import CycleSegment
    from app.models.syn_segment import SynSegment


class SynSegmentLink(Base):
    """Mapping from a synthetic route to the real segments it covers."""

    __tablename__ = "syn_segment_link"
    __table_args__ = (
        CheckConstraint("match_method IN ('street_name', 'manual')", name="syn_segment_link_match_method_check"),
    )

    syn_segment_id: Mapped[str] = mapped_column(Text, ForeignKey("syn_segment.id", ondelete="CASCADE"), primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("cycle_segment.id", ondelete="CASCADE"), primary_key=True)
    match_method: Mapped[str] = mapped_column(Text)

    syn_segment: Mapped[SynSegment] = relationship(back_populates="links")
    segment: Mapped[CycleSegment] = relationship(back_populates="syn_links")
