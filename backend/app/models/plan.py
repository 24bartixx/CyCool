from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.plan_item import PlanItem


class Plan(Base):
    """A saved optimiser scenario."""

    __tablename__ = "plan"
    __table_args__ = (
        CheckConstraint("budget_eur >= 0", name="plan_budget_eur_check"),
        CheckConstraint("goal IN ('comfort_km', 'temp_reduction', 'cyclists')", name="plan_goal_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    budget_eur: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    goal: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    total_capex_eur: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list[PlanItem]] = relationship(back_populates="plan", cascade="all, delete-orphan",
                                                 passive_deletes=True)
