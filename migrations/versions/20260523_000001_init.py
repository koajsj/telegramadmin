"""create initial tables

Revision ID: 20260523_000001
Revises:
Create Date: 2026-05-23 10:00:00
"""

from __future__ import annotations

from alembic import op

from bot.database.models import Base


revision = "20260523_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
