"""add learning candidates table

Revision ID: 20260523_000003
Revises: 20260523_000002
Create Date: 2026-05-23 17:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260523_000003"
down_revision = "20260523_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("candidate_type", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("normalized_value", sa.String(length=255), nullable=False),
        sa.Column("sample_value", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("confirm_count", sa.Integer(), nullable=False),
        sa.Column("false_positive_count", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("source_stats_json", sa.JSON(), nullable=False),
        sa.Column("lexicon_entry_id", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("rejected_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "candidate_type", "normalized_value", name="uq_learning_candidate_key"),
    )
    op.create_index("ix_learning_candidates_chat_id", "learning_candidates", ["chat_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_learning_candidates_chat_id", table_name="learning_candidates")
    op.drop_table("learning_candidates")
