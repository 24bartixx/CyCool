from sqlalchemy import CheckConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DataSource(Base):
    """Provenance of every layer: municipal, derived, synthetic or external."""

    __tablename__ = "data_source"
    __table_args__ = (
        CheckConstraint("origin IN ('municipal', 'derived', 'synthetic', 'external')", name="data_source_origin_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    origin: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
