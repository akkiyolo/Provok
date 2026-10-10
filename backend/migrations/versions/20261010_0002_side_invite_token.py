"""side invite token (private invite links)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-10 06:30:00+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('sides', sa.Column('invite_token', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('sides', 'invite_token')
