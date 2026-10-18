"""referrals: invite codes, who invited whom, settlement time

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-18 11:00:00+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('referral_code', sa.String(length=12), nullable=True))
    op.add_column('users', sa.Column('referred_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('users', sa.Column('referral_settled_at', sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(op.f('uq_users_referral_code'), 'users', ['referral_code'])
    op.create_index(op.f('ix_users_referred_by_id'), 'users', ['referred_by_id'], unique=False)
    op.create_foreign_key(op.f('fk_users_referred_by_id_users'), 'users', 'users', ['referred_by_id'], ['id'],
                          ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_users_referred_by_id_users'), 'users', type_='foreignkey')
    op.drop_index(op.f('ix_users_referred_by_id'), table_name='users')
    op.drop_constraint(op.f('uq_users_referral_code'), 'users', type_='unique')
    op.drop_column('users', 'referral_settled_at')
    op.drop_column('users', 'referred_by_id')
    op.drop_column('users', 'referral_code')
