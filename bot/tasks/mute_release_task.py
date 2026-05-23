from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging

from aiogram import Bot

from bot.app_context import AppContext
from bot.database import repositories
from bot.database.session import session_scope
from bot.services import moderation


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _run_once(bot: Bot, app_context: AppContext) -> None:
    since = _utc_now() - timedelta(days=app_context.settings.mute_auto_release_lookback_days)
    async for session in session_scope(app_context.session_factory):
        rows = await repositories.list_recent_mute_punishments(session, since=since, limit=1000)
    now = _utc_now()
    for row in rows:
        if row.duration_seconds is None or row.created_at is None:
            continue
        expires_at = row.created_at + timedelta(seconds=int(row.duration_seconds))
        if expires_at > now:
            continue
        async for session in session_scope(app_context.session_factory):
            already_done = await repositories.has_audit_action_for_punishment(
                session=session,
                action="mute_auto_release_executed",
                punishment_id=int(row.id),
            )
        if already_done:
            continue
        try:
            await moderation.unmute_user(bot=bot, chat_id=int(row.chat_id), user_id=int(row.user_id))
        except moderation.ModerationActionError as exc:
            async for session in session_scope(app_context.session_factory):
                await repositories.create_audit_log(
                    session=session,
                    chat_id=int(row.chat_id),
                    actor_user_id=None,
                    target_user_id=int(row.user_id),
                    action="mute_auto_release_failed",
                    detail_json={
                        "punishment_id": int(row.id),
                        "expires_at": expires_at.isoformat(),
                        "error": str(exc),
                    },
                )
            continue
        async for session in session_scope(app_context.session_factory):
            await repositories.create_audit_log(
                session=session,
                chat_id=int(row.chat_id),
                actor_user_id=None,
                target_user_id=int(row.user_id),
                action="mute_auto_release_executed",
                detail_json={
                    "punishment_id": int(row.id),
                    "expires_at": expires_at.isoformat(),
                },
            )


async def run_mute_release_loop(bot: Bot, app_context: AppContext) -> None:
    interval_seconds = app_context.settings.mute_auto_release_interval_seconds
    while True:
        try:
            await _run_once(bot, app_context)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "mute_release_loop_failed",
                extra={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        await asyncio.sleep(interval_seconds)
