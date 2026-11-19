from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.data_source import DataSource


class InterventionType(Base):
    """Synthetic VAS-R1 catalogue entry with cost and cooling effect."""

    __tablename__ = "intervention_type"
    __table_args__ = (
        CheckConstraint("unit_kind IN ('per_100m', 'per_site', 'city_wide', 'reference')",
                        name="intervention_type_unit_kind_check"),
        CheckConstraint("applies_to IN ('segment', 'junction', 'station', 'network')",
                        name="intervention_type_applies_to_check"),
        CheckConstraint("capex_eur >= 0", name="intervention_type_capex_eur_check"),
        CheckConstraint("opex_eur_yr >= 0", name="intervention_type_opex_eur_yr_check"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # INT-01..08
    source_id: Mapped[int] = mapped_column(ForeignKey("data_source.id"))
    category: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    unit_label: Mapped[str] = mapped_column(Text)
    unit_kind: Mapped[str] = mapped_column(Text)
    applies_to: Mapped[str] = mapped_column(Text)
    capex_eur: Mapped[int]
    opex_eur_yr: Mapped[int]
    surface_temp_reduction_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    utci_improvement_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    co2_kg_yr: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    deployment_weeks: Mapped[int | None]
    notes: Mapped[str | None] = mapped_column(Text)

    source: Mapped[DataSource] = relationship()
