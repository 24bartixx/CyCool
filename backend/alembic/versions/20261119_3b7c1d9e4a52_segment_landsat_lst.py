"""segment landsat lst

Revision ID: 3b7c1d9e4a52
Revises: 8edba03e4df0
Create Date: 2026-11-19 23:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '3b7c1d9e4a52'
down_revision: str | Sequence[str] | None = '8edba03e4df0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('segment_metrics', sa.Column('lst_summer_c', sa.Numeric(precision=5, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column('segment_metrics', 'lst_summer_c')
