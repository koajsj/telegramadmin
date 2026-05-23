from __future__ import annotations

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery

from bot.app_context import AppContext
from bot.database import repositories
from bot.database.session import session_scope
from bot.services import moderation


router = Router(name="callbacks")


class ModerateAction(CallbackData, prefix="md"):
    action: str
    chat_id: int
    user_id: int


@router.callback_query(ModerateAction.filter())
async def on_moderate_callback(query: CallbackQuery, callback_data: ModerateAction, app_context: AppContext) -> None:
    actor = query.from_user
    if actor.id not in app_context.settings.admin_ids:
        await query.answer("无权限", show_alert=True)
        return

    action = callback_data.action
    chat_id = callback_data.chat_id
    user_id = callback_data.user_id

    if action == "ignore":
        await query.answer("已忽略")
        return

    if action == "warn":
        async for session in session_scope(app_context.session_factory):
            await repositories.create_punishment(
                session=session,
                violation_id=None,
                chat_id=chat_id,
                user_id=user_id,
                action="warn",
                duration_seconds=None,
                reason="inline_warn",
                executed_by=actor.id,
            )
            await repositories.increment_violation_stats(session, chat_id, user_id, "warn")
        await query.answer("已警告")
        return

    if action == "mute10":
        await moderation.mute_user(query.bot, chat_id, user_id, 600)
        async for session in session_scope(app_context.session_factory):
            await repositories.create_punishment(
                session=session,
                violation_id=None,
                chat_id=chat_id,
                user_id=user_id,
                action="mute",
                duration_seconds=600,
                reason="inline_mute10",
                executed_by=actor.id,
            )
            await repositories.increment_violation_stats(session, chat_id, user_id, "mute")
        await query.answer("已禁言10分钟")
        return

    if action == "mute60":
        await moderation.mute_user(query.bot, chat_id, user_id, 3600)
        async for session in session_scope(app_context.session_factory):
            await repositories.create_punishment(
                session=session,
                violation_id=None,
                chat_id=chat_id,
                user_id=user_id,
                action="mute",
                duration_seconds=3600,
                reason="inline_mute60",
                executed_by=actor.id,
            )
            await repositories.increment_violation_stats(session, chat_id, user_id, "mute")
        await query.answer("已禁言1小时")
        return

    if action == "ban":
        await moderation.ban_user(query.bot, chat_id, user_id)
        async for session in session_scope(app_context.session_factory):
            await repositories.create_punishment(
                session=session,
                violation_id=None,
                chat_id=chat_id,
                user_id=user_id,
                action="ban",
                duration_seconds=None,
                reason="inline_ban",
                executed_by=actor.id,
            )
            await repositories.increment_violation_stats(session, chat_id, user_id, "ban")
        await query.answer("已封禁")
        return

    if action == "wl":
        async for session in session_scope(app_context.session_factory):
            await repositories.add_whitelist_user(session, chat_id, user_id)
        await query.answer("已加入白名单")
        return

    await query.answer("不支持的操作", show_alert=True)
