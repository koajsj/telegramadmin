from __future__ import annotations

from datetime import datetime, timezone
import re

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import Message

from bot.app_context import AppContext
from bot.database import repositories
from bot.database.session import session_scope
from bot.services import moderation


router = Router(name="commands")


def _parse_user_id_from_text(text: str) -> int | None:
    parts = text.strip().split()
    if len(parts) < 2:
        return None
    raw = parts[1].strip()
    if raw.startswith("@"):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_duration_seconds(text: str) -> int | None:
    parts = text.strip().split()
    if len(parts) < 2:
        return None
    raw = parts[-1].strip().lower()
    if raw.isdigit():
        return int(raw)
    match = re.fullmatch(r"(\d+)([mhd])", raw)
    if match is None:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "m":
        return amount * 60
    if unit == "h":
        return amount * 3600
    if unit == "d":
        return amount * 86400
    return None


async def _is_group_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    return member.status in {"creator", "administrator"}


async def _require_admin(message: Message, app_context: AppContext) -> bool:
    user = message.from_user
    chat = message.chat
    if user is None or chat is None:
        return False
    if user.id in app_context.settings.admin_ids:
        return True
    if chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return await _is_group_admin(message.bot, chat.id, user.id)
    return False


async def _target_user(message: Message) -> int | None:
    reply = message.reply_to_message
    if reply is not None and reply.from_user is not None:
        return reply.from_user.id
    text = message.text or ""
    return _parse_user_id_from_text(text)


@router.message(Command("start"))
async def start_command(message: Message) -> None:
    await message.answer("机器人已在线。使用 /help 查看管理命令。")


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    help_text = (
        "可用命令:\n"
        "/start /help /settings /status\n"
        "/warn <user_id> 或回复消息 /warn\n"
        "/mute <user_id> <10m|1h|1d> 或回复消息 /mute 10m\n"
        "/ban <user_id> 或回复消息 /ban\n"
        "/unban <user_id>\n"
        "/history <user_id>\n"
        "/whitelist <user_id>\n"
        "/blacklist <user_id> [reason]"
    )
    await message.answer(help_text)


@router.message(Command("settings"))
@router.message(Command("status"))
async def settings_command(message: Message, app_context: AppContext) -> None:
    chat = message.chat
    if chat is None:
        return

    async for session in session_scope(app_context.session_factory):
        model = await repositories.ensure_chat(
            session=session,
            chat_id=chat.id,
            title=chat.title,
            default_log_chat_id=app_context.settings.default_log_chat_id,
            newcomer_watch_seconds=app_context.settings.newcomer_watch_seconds,
        )
        text = (
            f"chat_id={model.id}\n"
            f"newcomer_restrict_enabled={model.newcomer_restrict_enabled}\n"
            f"newcomer_watch_seconds={model.newcomer_watch_seconds}\n"
            f"allow_links={model.allow_links}\n"
            f"allow_media={model.allow_media}\n"
            f"keyword_filter_enabled={model.keyword_filter_enabled}\n"
            f"link_filter_enabled={model.link_filter_enabled}\n"
            f"flood_enabled={model.flood_enabled}\n"
            f"log_chat_id={model.log_chat_id}"
        )
        await message.answer(text)


@router.message(Command("warn"))
async def warn_command(message: Message, app_context: AppContext) -> None:
    if not await _require_admin(message, app_context):
        await message.answer("无权限。")
        return

    target_user_id = await _target_user(message)
    if target_user_id is None:
        await message.answer("用法: /warn <user_id> 或回复目标消息执行 /warn")
        return

    chat = message.chat
    actor = message.from_user
    if chat is None:
        return

    async for session in session_scope(app_context.session_factory):
        await repositories.create_punishment(
            session=session,
            violation_id=None,
            chat_id=chat.id,
            user_id=target_user_id,
            action="warn",
            duration_seconds=None,
            reason="manual_warn",
            executed_by=actor.id if actor is not None else None,
        )
        await repositories.increment_violation_stats(session, chat.id, target_user_id, "warn")
        await repositories.create_audit_log(
            session=session,
            chat_id=chat.id,
            actor_user_id=actor.id if actor is not None else None,
            target_user_id=target_user_id,
            action="manual_warn",
            detail_json={"source": "command"},
        )
    await message.answer(f"已警告用户 {target_user_id}")


@router.message(Command("mute"))
async def mute_command(message: Message, app_context: AppContext) -> None:
    if not await _require_admin(message, app_context):
        await message.answer("无权限。")
        return

    target_user_id = await _target_user(message)
    duration_seconds = _parse_duration_seconds(message.text or "")
    if target_user_id is None or duration_seconds is None:
        await message.answer("用法: /mute <user_id> <10m|1h|1d> 或回复目标消息 /mute 10m")
        return

    chat = message.chat
    actor = message.from_user
    if chat is None:
        return

    await moderation.mute_user(message.bot, chat.id, target_user_id, duration_seconds)
    async for session in session_scope(app_context.session_factory):
        await repositories.create_punishment(
            session=session,
            violation_id=None,
            chat_id=chat.id,
            user_id=target_user_id,
            action="mute",
            duration_seconds=duration_seconds,
            reason="manual_mute",
            executed_by=actor.id if actor is not None else None,
        )
        await repositories.increment_violation_stats(session, chat.id, target_user_id, "mute")
    await message.answer(f"已禁言用户 {target_user_id} {duration_seconds} 秒")


@router.message(Command("ban"))
async def ban_command(message: Message, app_context: AppContext) -> None:
    if not await _require_admin(message, app_context):
        await message.answer("无权限。")
        return

    target_user_id = await _target_user(message)
    if target_user_id is None:
        await message.answer("用法: /ban <user_id> 或回复目标消息 /ban")
        return

    chat = message.chat
    actor = message.from_user
    if chat is None:
        return

    await moderation.ban_user(message.bot, chat.id, target_user_id)
    async for session in session_scope(app_context.session_factory):
        await repositories.create_punishment(
            session=session,
            violation_id=None,
            chat_id=chat.id,
            user_id=target_user_id,
            action="ban",
            duration_seconds=None,
            reason="manual_ban",
            executed_by=actor.id if actor is not None else None,
        )
        await repositories.increment_violation_stats(session, chat.id, target_user_id, "ban")
    await message.answer(f"已封禁用户 {target_user_id}")


@router.message(Command("unban"))
async def unban_command(message: Message, app_context: AppContext) -> None:
    if not await _require_admin(message, app_context):
        await message.answer("无权限。")
        return

    user_id = _parse_user_id_from_text(message.text or "")
    if user_id is None:
        await message.answer("用法: /unban <user_id>")
        return

    chat = message.chat
    actor = message.from_user
    if chat is None:
        return

    await moderation.unban_user(message.bot, chat.id, user_id)
    async for session in session_scope(app_context.session_factory):
        await repositories.create_punishment(
            session=session,
            violation_id=None,
            chat_id=chat.id,
            user_id=user_id,
            action="unban",
            duration_seconds=None,
            reason="manual_unban",
            executed_by=actor.id if actor is not None else None,
        )
    await message.answer(f"已解封用户 {user_id}")


@router.message(Command("history"))
async def history_command(message: Message, app_context: AppContext) -> None:
    if not await _require_admin(message, app_context):
        await message.answer("无权限。")
        return

    target_user_id = _parse_user_id_from_text(message.text or "")
    if target_user_id is None:
        await message.answer("用法: /history <user_id>")
        return

    chat = message.chat
    if chat is None:
        return

    async for session in session_scope(app_context.session_factory):
        rows = await repositories.list_user_history(session, chat.id, target_user_id, 10)
        if len(rows) == 0:
            await message.answer("暂无处罚历史")
            return
        lines = [f"{item.created_at} | {item.action} | {item.reason}" for item in rows]
        await message.answer("\n".join(lines))


@router.message(Command("whitelist"))
async def whitelist_command(message: Message, app_context: AppContext) -> None:
    if not await _require_admin(message, app_context):
        await message.answer("无权限。")
        return
    target_user_id = _parse_user_id_from_text(message.text or "")
    if target_user_id is None:
        await message.answer("用法: /whitelist <user_id>")
        return

    chat = message.chat
    if chat is None:
        return

    async for session in session_scope(app_context.session_factory):
        created = await repositories.add_whitelist_user(session, chat.id, target_user_id)
    if created:
        await message.answer(f"用户 {target_user_id} 已加入白名单")
        return
    await message.answer("该用户已在白名单")


@router.message(Command("blacklist"))
async def blacklist_command(message: Message, app_context: AppContext) -> None:
    if not await _require_admin(message, app_context):
        await message.answer("无权限。")
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("用法: /blacklist <user_id> [reason]")
        return

    try:
        target_user_id = int(parts[1])
    except ValueError:
        await message.answer("user_id 必须是整数")
        return

    reason = parts[2] if len(parts) >= 3 else "manual_blacklist"
    chat = message.chat
    if chat is None:
        return

    async for session in session_scope(app_context.session_factory):
        created = await repositories.add_blacklist_user(session, chat.id, target_user_id, reason)
    if created:
        await message.answer(f"用户 {target_user_id} 已加入黑名单")
        return
    await message.answer("该用户已在黑名单")
