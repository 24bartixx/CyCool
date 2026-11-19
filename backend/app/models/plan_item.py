from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from geoalchemy2 import WKBElement
from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, point_geometry

if TYPE_CHECKING:
    from app.models.ambici_station import AmbiciStation
    from app.models.cycle_segment import CycleSegment
    from app.models.intervention_type import InterventionType
    from app.models.plan import Plan


class PlanItem(Base):
    """One intervention placed by a plan, on a segment, at a station or at a new point."""

    __tablename__ = "plan_item"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="plan_item_quantity_check"),
        Index("plan_item_plan_idx", "plan_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan.id", ondelete="CASCADE"))
    intervention_id: Mapped[str] = mapped_column(Text, ForeignKey("intervention_type.id"))
    segment_id: Mapped[int | None] = mapped_column(ForeignKey("cycle_segment.id"))
    ambici_station_id: Mapped[int | None] = mapped_column(ForeignKey("ambici_station.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), server_default=text("1"))
    capex_eur: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    geom: Mapped[WKBElement | None] = mapped_column(point_geometry())  # site of a new fountain/shelter

    plan: Mapped[Plan] = relationship(back_populates="items")
    intervention: Mapped[InterventionType] = relationship()
    segment: Mapped[CycleSegment | None] = relationship()
    ambici_station: Mapped[AmbiciStation | None] = relationship()
