"""add created_at to verification_sessions

Revision ID: 20260523_000002
Revises: 20260523_000001
Create Date: 2026-05-23 18:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260523_000002"
down_revision = "20260523_000001"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    columns = inspector.get_columns(table_name)
    names = {item["name"] for item in columns}
    return column_name in names


def upgrade() -> None:
    if _has_column("verification_sessions", "created_at"):
        return
    op.add_column(
        "verification_sessions",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    if not _has_column("verification_sessions", "created_at"):
        return
    op.drop_column("verification_sessions", "created_at")
