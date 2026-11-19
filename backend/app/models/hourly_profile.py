from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.data_source import DataSource


class HourlyProfile(Base):
    """Synthetic city-wide summer day: temperature, radiation, UTCI by street type, cyclist flow."""

    __tablename__ = "hourly_profile"
    __table_args__ = (CheckConstraint("hour BETWEEN 0 AND 23", name="hourly_profile_hour_check"),)

    hour: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_source.id"))
    air_temp_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    rel_humidity_pct: Mapped[int | None]
    solar_radiation_wm2: Mapped[int | None]
    utci_unshaded_asphalt_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    utci_building_shaded_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    utci_shaded_park_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    utci_cool_lane_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    cyclist_flow_spring: Mapped[int | None]
    cyclist_flow_summer: Mapped[int | None]

    source: Mapped[DataSource] = relationship()
