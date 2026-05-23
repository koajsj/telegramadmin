from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message

from bot.app_context import AppContext
from bot.database import repositories
from bot.database.session import session_scope
from bot.keyboards.moderation import build_log_actions
from bot.services import audit_log, moderation, onboarding, rule_engine
from bot.services.keywords import load_keywords_from_directory


router = Router(name="messages")


KEYWORD_SCORE = 60
LINK_SCORE = 35
FLOOD_SCORE = 35


async def _is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    return member.status in {"creator", "administrator"}


@router.message(F.new_chat_members)
async def on_new_members(message: Message, app_context: AppContext) -> None:
    chat = message.chat
    if chat is None:
        return

    members = message.new_chat_members
    if members is None:
        return

    for member in members:
        async for session in session_scope(app_context.session_factory):
            await repositories.ensure_chat(
                session=session,
                chat_id=chat.id,
                title=chat.title,
                default_log_chat_id=app_context.settings.default_log_chat_id,
                newcomer_watch_seconds=app_context.settings.newcomer_watch_seconds,
            )
            await repositories.ensure_user(
                session=session,
                user_id=member.id,
                username=member.username,
                full_name=member.full_name,
                is_bot=member.is_bot,
                language_code=member.language_code,
            )
            await repositories.ensure_chat_member(
                session=session,
                chat_id=chat.id,
                user_id=member.id,
                joined_at=datetime.now(timezone.utc),
                is_newcomer=True,
            )

        await message.answer(f"欢迎 {member.full_name} 加入，请先阅读群规。")


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def on_group_message(message: Message, app_context: AppContext) -> None:
    user = message.from_user
    chat = message.chat
    if user is None or chat is None or user.is_bot:
        return

    if user.id in app_context.settings.admin_ids:
        return

    if await _is_chat_admin(message.bot, chat.id, user.id):
        return

    text = message.text or message.caption or ""
    if text == "" and not onboarding.message_has_media(message):
        return

    keywords = load_keywords_from_directory(app_context.keyword_files_dir)

    async for session in session_scope(app_context.session_factory):
        chat_model = await repositories.ensure_chat(
            session=session,
            chat_id=chat.id,
            title=chat.title,
            default_log_chat_id=app_context.settings.default_log_chat_id,
            newcomer_watch_seconds=app_context.settings.newcomer_watch_seconds,
        )
        await repositories.ensure_user(
            session=session,
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            is_bot=user.is_bot,
            language_code=user.language_code,
        )
        member = await repositories.ensure_chat_member(
            session=session,
            chat_id=chat.id,
            user_id=user.id,
            joined_at=None,
            is_newcomer=True,
        )
        await repositories.mark_member_first_message(session, member, datetime.now(timezone.utc))
        await repositories.increment_message_stats(session, chat.id, user.id)

        blacklisted = await repositories.is_user_blacklisted(session, chat.id, user.id)
        if blacklisted:
            await moderation.try_delete_message(message)
            await moderation.ban_user(message.bot, chat.id, user.id)
            await repositories.create_violation(
                session=session,
                chat_id=chat.id,
                user_id=user.id,
                message_id=message.message_id,
                rule_name="blacklist_user",
                reason="blacklist_user",
                content_excerpt=text[:200],
                score=100,
                rule_id=None,
            )
            await repositories.create_punishment(
                session=session,
                violation_id=None,
                chat_id=chat.id,
                user_id=user.id,
                action="ban",
                duration_seconds=None,
                reason="blacklist_user",
                executed_by=None,
            )
            await repositories.increment_violation_stats(session, chat.id, user.id, "ban")
            await audit_log.send_log(message.bot, chat_model.log_chat_id, chat.id, user.id, "blacklist_user", 100, "ban", text)
            return

        whitelisted = await repositories.is_user_whitelisted(session, chat.id, user.id)
        if whitelisted:
            return

        newcomer_reason = None
        if chat_model.newcomer_restrict_enabled:
            newcomer_reason = onboarding.newcomer_violation_reason(
                message=message,
                text=text,
                joined_at=member.joined_at,
                watch_seconds=chat_model.newcomer_watch_seconds,
                allow_links=chat_model.allow_links,
                allow_media=chat_model.allow_media,
            )
        if newcomer_reason is not None:
            await moderation.try_delete_message(message)
            violation = await repositories.create_violation(
                session=session,
                chat_id=chat.id,
                user_id=user.id,
                message_id=message.message_id,
                rule_name="newcomer_restriction",
                reason=newcomer_reason,
                content_excerpt=text[:200],
                score=45,
                rule_id=None,
            )
            decision = moderation.decide_escalation(
                violation_count=await repositories.count_recent_violations(session, chat.id, user.id, 24),
                mute_minutes_step3=app_context.settings.mute_minutes_step3,
                mute_hours_step4=app_context.settings.mute_hours_step4,
            )
            action = await moderation.apply_decision(message.bot, chat.id, user.id, decision)
            await repositories.create_punishment(
                session=session,
                violation_id=violation.id,
                chat_id=chat.id,
                user_id=user.id,
                action=action,
                duration_seconds=decision.duration_seconds,
                reason=decision.reason,
                executed_by=None,
            )
            await repositories.increment_violation_stats(session, chat.id, user.id, action)
            await audit_log.send_log(
                message.bot,
                chat_model.log_chat_id,
                chat.id,
                user.id,
                newcomer_reason,
                45,
                action,
                text,
            )
            return

        hits = await rule_engine.evaluate_message(
            redis_client=app_context.redis,
            chat_id=chat.id,
            user_id=user.id,
            text=text,
            keywords=keywords,
            keyword_score=KEYWORD_SCORE,
            link_score=LINK_SCORE,
            flood_score=FLOOD_SCORE,
            flood_window_seconds=app_context.settings.flood_window_seconds,
            flood_max_messages=app_context.settings.flood_max_messages,
        )

        if len(hits) == 0:
            return

        total_score = sum(item.score for item in hits)
        reason_text = ",".join(item.reason for item in hits)

        deleted = await moderation.try_delete_message(message)
        if not deleted:
            return

        violation = await repositories.create_violation(
            session=session,
            chat_id=chat.id,
            user_id=user.id,
            message_id=message.message_id,
            rule_name=hits[0].rule_name,
            reason=reason_text,
            content_excerpt=text[:200],
            score=total_score,
            rule_id=None,
        )
        violation_count = await repositories.count_recent_violations(session, chat.id, user.id, 24)
        decision = moderation.decide_escalation(
            violation_count=violation_count,
            mute_minutes_step3=app_context.settings.mute_minutes_step3,
            mute_hours_step4=app_context.settings.mute_hours_step4,
        )

        action = await moderation.apply_decision(message.bot, chat.id, user.id, decision)
        await repositories.create_punishment(
            session=session,
            violation_id=violation.id,
            chat_id=chat.id,
            user_id=user.id,
            action=action,
            duration_seconds=decision.duration_seconds,
            reason=decision.reason,
            executed_by=None,
        )
        await repositories.increment_violation_stats(session, chat.id, user.id, action)

        if action == "warn":
            await message.answer(f"用户 {user.id} 已警告。")

        await audit_log.send_log(
            bot=message.bot,
            log_chat_id=chat_model.log_chat_id,
            chat_id=chat.id,
            user_id=user.id,
            reason=reason_text,
            score=total_score,
            action=audit_log.build_action_text(action, decision.duration_seconds),
            excerpt=text,
        )

        if chat_model.log_chat_id is not None:
            await message.bot.send_message(
                chat_id=chat_model.log_chat_id,
                text=f"快捷处置: chat={chat.id} user={user.id}",
                reply_markup=build_log_actions(chat.id, user.id),
            )
