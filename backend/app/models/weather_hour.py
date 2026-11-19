from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.data_source import DataSource


class WeatherHour(Base):
    """Real hourly summer weather at Viladecans (ERA5 reanalysis via Open-Meteo), input of the UTCI model."""

    __tablename__ = "weather_hour"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=False), primary_key=True)  # local time, Europe/Madrid
    source_id: Mapped[int] = mapped_column(ForeignKey("data_source.id"))
    temp_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    rh_pct: Mapped[int] = mapped_column(SmallInteger)
    wind_ms: Mapped[Decimal] = mapped_column(Numeric(5, 2))  # at 10 m
    ghi_wm2: Mapped[Decimal] = mapped_column(Numeric(6, 1))  # global horizontal
    dhi_wm2: Mapped[Decimal] = mapped_column(Numeric(6, 1))  # diffuse horizontal
    direct_h_wm2: Mapped[Decimal] = mapped_column(Numeric(6, 1))  # direct on a horizontal plane
    dni_wm2: Mapped[Decimal] = mapped_column(Numeric(6, 1))  # direct normal

    source: Mapped[DataSource] = relationship()
