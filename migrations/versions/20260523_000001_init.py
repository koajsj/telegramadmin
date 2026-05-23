"""create initial tables

Revision ID: 20260523_000001
Revises:
Create Date: 2026-05-23 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260523_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chats",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("log_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("newcomer_restrict_enabled", sa.Boolean(), nullable=False),
        sa.Column("newcomer_watch_seconds", sa.Integer(), nullable=False),
        sa.Column("allow_links", sa.Boolean(), nullable=False),
        sa.Column("allow_media", sa.Boolean(), nullable=False),
        sa.Column("keyword_filter_enabled", sa.Boolean(), nullable=False),
        sa.Column("flood_enabled", sa.Boolean(), nullable=False),
        sa.Column("link_filter_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_bot", sa.Boolean(), nullable=False),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("rule_type", sa.String(length=32), nullable=False),
        sa.Column("trigger_json", sa.JSON(), nullable=False),
        sa.Column("target_user_type", sa.String(length=32), nullable=False),
        sa.Column("newcomer_only", sa.Boolean(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rules_chat_id", "rules", ["chat_id"], unique=False)

    op.create_table(
        "chat_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restricted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_newcomer", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "user_id", name="uq_chat_member_chat_user"),
    )

    op.create_table(
        "violations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column("rule_name", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("content_excerpt", sa.Text(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_violations_chat_id", "violations", ["chat_id"], unique=False)
    op.create_index("ix_violations_user_id", "violations", ["user_id"], unique=False)

    op.create_table(
        "punishments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("violation_id", sa.Integer(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("executed_by", sa.BigInteger(), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("revoked_by", sa.BigInteger(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["violation_id"], ["violations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_punishments_chat_id", "punishments", ["chat_id"], unique=False)
    op.create_index("ix_punishments_user_id", "punishments", ["user_id"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("target_user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("detail_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_chat_id", "audit_logs", ["chat_id"], unique=False)
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"], unique=False)
    op.create_index("ix_audit_logs_target_user_id", "audit_logs", ["target_user_id"], unique=False)

    op.create_table(
        "whitelist_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "user_id", name="uq_whitelist_chat_user"),
    )
    op.create_index("ix_whitelist_users_chat_id", "whitelist_users", ["chat_id"], unique=False)
    op.create_index("ix_whitelist_users_user_id", "whitelist_users", ["user_id"], unique=False)

    op.create_table(
        "blacklist_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "user_id", name="uq_blacklist_chat_user"),
    )
    op.create_index("ix_blacklist_users_chat_id", "blacklist_users", ["chat_id"], unique=False)
    op.create_index("ix_blacklist_users_user_id", "blacklist_users", ["user_id"], unique=False)

    op.create_table(
        "whitelist_domains",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "domain", name="uq_whitelist_chat_domain"),
    )
    op.create_index("ix_whitelist_domains_chat_id", "whitelist_domains", ["chat_id"], unique=False)

    op.create_table(
        "blacklist_domains",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "domain", name="uq_blacklist_chat_domain"),
    )
    op.create_index("ix_blacklist_domains_chat_id", "blacklist_domains", ["chat_id"], unique=False)

    op.create_table(
        "invite_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("invite_link", sa.Text(), nullable=True),
        sa.Column("invite_link_creator_id", sa.BigInteger(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invite_sources_chat_id", "invite_sources", ["chat_id"], unique=False)
    op.create_index("ix_invite_sources_user_id", "invite_sources", ["user_id"], unique=False)

    op.create_table(
        "message_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("total_messages", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_violations", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_warns", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_mutes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_bans", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "user_id", name="uq_message_stats_chat_user"),
    )
    op.create_index("ix_message_stats_chat_id", "message_stats", ["chat_id"], unique=False)
    op.create_index("ix_message_stats_user_id", "message_stats", ["user_id"], unique=False)

    op.create_table(
        "verification_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("challenge", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "user_id", name="uq_verification_chat_user"),
    )
    op.create_index("ix_verification_sessions_chat_id", "verification_sessions", ["chat_id"], unique=False)
    op.create_index("ix_verification_sessions_user_id", "verification_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_verification_sessions_user_id", table_name="verification_sessions")
    op.drop_index("ix_verification_sessions_chat_id", table_name="verification_sessions")
    op.drop_table("verification_sessions")

    op.drop_index("ix_message_stats_user_id", table_name="message_stats")
    op.drop_index("ix_message_stats_chat_id", table_name="message_stats")
    op.drop_table("message_stats")

    op.drop_index("ix_invite_sources_user_id", table_name="invite_sources")
    op.drop_index("ix_invite_sources_chat_id", table_name="invite_sources")
    op.drop_table("invite_sources")

    op.drop_index("ix_blacklist_domains_chat_id", table_name="blacklist_domains")
    op.drop_table("blacklist_domains")

    op.drop_index("ix_whitelist_domains_chat_id", table_name="whitelist_domains")
    op.drop_table("whitelist_domains")

    op.drop_index("ix_blacklist_users_user_id", table_name="blacklist_users")
    op.drop_index("ix_blacklist_users_chat_id", table_name="blacklist_users")
    op.drop_table("blacklist_users")

    op.drop_index("ix_whitelist_users_user_id", table_name="whitelist_users")
    op.drop_index("ix_whitelist_users_chat_id", table_name="whitelist_users")
    op.drop_table("whitelist_users")

    op.drop_index("ix_audit_logs_target_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_chat_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_punishments_user_id", table_name="punishments")
    op.drop_index("ix_punishments_chat_id", table_name="punishments")
    op.drop_table("punishments")

    op.drop_index("ix_violations_user_id", table_name="violations")
    op.drop_index("ix_violations_chat_id", table_name="violations")
    op.drop_table("violations")

    op.drop_table("chat_members")

    op.drop_index("ix_rules_chat_id", table_name="rules")
    op.drop_table("rules")

    op.drop_table("users")
    op.drop_table("chats")
