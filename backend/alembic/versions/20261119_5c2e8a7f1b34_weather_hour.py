"""weather hour

Revision ID: 5c2e8a7f1b34
Revises: 3b7c1d9e4a52
Create Date: 2026-11-19 23:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '5c2e8a7f1b34'
down_revision: str | Sequence[str] | None = '3b7c1d9e4a52'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('weather_hour',
    sa.Column('time', sa.DateTime(timezone=False), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('temp_c', sa.Numeric(precision=4, scale=1), nullable=False),
    sa.Column('rh_pct', sa.SmallInteger(), nullable=False),
    sa.Column('wind_ms', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('ghi_wm2', sa.Numeric(precision=6, scale=1), nullable=False),
    sa.Column('dhi_wm2', sa.Numeric(precision=6, scale=1), nullable=False),
    sa.Column('direct_h_wm2', sa.Numeric(precision=6, scale=1), nullable=False),
    sa.Column('dni_wm2', sa.Numeric(precision=6, scale=1), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['data_source.id'], ),
    sa.PrimaryKeyConstraint('time')
    )


def downgrade() -> None:
    op.drop_table('weather_hour')
