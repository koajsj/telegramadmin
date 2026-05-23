from __future__ import annotations

import re

from aiogram.filters import Command
from aiogram.types import Message
from aiogram import Router

from bot.app_context import AppContext
from bot.database import repositories
from bot.database.session import session_scope
from bot.schemas.permissions import PermissionAction, PermissionDecision
from bot.services import moderation
from bot.services.management_audit import log_management_event
from bot.utils.permissions import authorize_action


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


async def _target_user(message: Message) -> int | None:
    reply = message.reply_to_message
    if reply is not None and reply.from_user is not None:
        return reply.from_user.id
    text = message.text or ""
    return _parse_user_id_from_text(text)


async def _authorize_management_command(
    message: Message,
    app_context: AppContext,
    action: PermissionAction,
    duration_seconds: int | None,
    target_user_id: int | None,
) -> PermissionDecision | None:
    user = message.from_user
    chat = message.chat
    if user is None or chat is None:
        return None

    decision = await authorize_action(
        bot=message.bot,
        settings=app_context.settings,
        user_id=user.id,
        chat_id=chat.id,
        action=action,
        duration_seconds=duration_seconds,
    )
    if decision.allowed:
        return decision

    async for session in session_scope(app_context.session_factory):
        await log_management_event(
            session=session,
            chat_id=chat.id,
            actor_user_id=user.id,
            target_user_id=target_user_id,
            action=f"cmd_{action.value}",
            decision=decision,
            detail_json={"status": "denied"},
        )
    await message.answer("无权限。")
    return None


@router.message(Command("start"))
async def start_command(message: Message) -> None:
    if message.chat is not None and message.chat.type == "private":
        return
    await message.answer("机器人已在线。使用 /help 查看管理命令。")


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    help_text = (
        "可用命令（含功能说明）:\n"
        "/start 打开机器人入口\n"
        "/panel 打开私聊群管理面板\n"
        "/help 查看命令说明\n"
        "/settings 查看当前群配置\n"
        "/status 查看运行/配置状态\n"
        "/warn <user_id> 警告用户\n"
        "/mute <user_id> <10m|1h|1d> 禁言用户\n"
        "/ban <user_id> 封禁用户（仅Owner）\n"
        "/unban <user_id> 解封用户（仅Owner）\n"
        "/history <user_id> 查看处罚历史\n"
        "/whitelist <user_id> 加入白名单（仅Owner）\n"
        "/blacklist <user_id> [reason] 加入黑名单（仅Owner）\n"
        "/setlog <log_chat_id> 设置日志群（仅Owner）\n"
        "/reloadkeywords 刷新词库（仅Owner）"
    )
    await message.answer(help_text)


@router.message(Command("settings"))
@router.message(Command("status"))
async def settings_command(message: Message, app_context: AppContext) -> None:
    chat = message.chat
    user = message.from_user
    if chat is None or user is None:
        return

    decision = await _authorize_management_command(
        message=message,
        app_context=app_context,
        action=PermissionAction.VIEW_SETTINGS,
        duration_seconds=None,
        target_user_id=None,
    )
    if decision is None:
        return

    async for session in session_scope(app_context.session_factory):
        model = await repositories.ensure_chat(
            session=session,
            chat_id=chat.id,
            title=chat.title,
            default_log_chat_id=app_context.settings.default_log_chat_id,
            newcomer_watch_seconds=app_context.settings.newcomer_watch_seconds,
        )
        await log_management_event(
            session=session,
            chat_id=chat.id,
            actor_user_id=user.id,
            target_user_id=None,
            action="cmd_view_settings",
            decision=decision,
            detail_json={"status": "success"},
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


@router.message(Command("reloadkeywords"))
async def reload_keywords_command(message: Message, app_context: AppContext) -> None:
    user = message.from_user
    chat = message.chat
    if user is None or chat is None:
        return

    decision = await _authorize_management_command(
        message=message,
        app_context=app_context,
        action=PermissionAction.RELOAD_KEYWORDS,
        duration_seconds=None,
        target_user_id=None,
    )
    if decision is None:
        return

    keywords = app_context.keyword_store.force_reload()
    async for session in session_scope(app_context.session_factory):
        await log_management_event(
            session=session,
            chat_id=chat.id,
            actor_user_id=user.id,
            target_user_id=None,
            action="cmd_reload_keywords",
            decision=decision,
            detail_json={"status": "success", "keyword_count": len(keywords)},
        )
    await message.answer(f"词库已刷新，共 {len(keywords)} 个关键词")


@router.message(Command("setlog"))
async def set_log_command(message: Message, app_context: AppContext) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("用法: /setlog <log_chat_id>")
        return
    try:
        log_chat_id = int(parts[1])
    except ValueError:
        await message.answer("log_chat_id 必须是整数")
        return

    chat = message.chat
    user = message.from_user
    if chat is None or user is None:
        return

    decision = await _authorize_management_command(
        message=message,
        app_context=app_context,
        action=PermissionAction.SET_LOG,
        duration_seconds=None,
        target_user_id=None,
    )
    if decision is None:
        return

    async for session in session_scope(app_context.session_factory):
        await repositories.ensure_chat(
            session=session,
            chat_id=chat.id,
            title=chat.title,
            default_log_chat_id=app_context.settings.default_log_chat_id,
            newcomer_watch_seconds=app_context.settings.newcomer_watch_seconds,
        )
        await repositories.update_chat_log_chat(session, chat.id, log_chat_id)
        await log_management_event(
            session=session,
            chat_id=chat.id,
            actor_user_id=user.id,
            target_user_id=None,
            action="cmd_set_log",
            decision=decision,
            detail_json={"status": "success", "log_chat_id": log_chat_id},
        )
    await message.answer(f"日志群已更新为 {log_chat_id}")


@router.message(Command("warn"))
async def warn_command(message: Message, app_context: AppContext) -> None:
    target_user_id = await _target_user(message)
    if target_user_id is None:
        await message.answer("用法: /warn <user_id> 或回复目标消息执行 /warn")
        return

    chat = message.chat
    actor = message.from_user
    if chat is None or actor is None:
        return

    decision = await _authorize_management_command(
        message=message,
        app_context=app_context,
        action=PermissionAction.WARN,
        duration_seconds=None,
        target_user_id=target_user_id,
    )
    if decision is None:
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
            executed_by=actor.id,
        )
        await repositories.increment_violation_stats(session, chat.id, target_user_id, "warn")
        await log_management_event(
            session=session,
            chat_id=chat.id,
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            action="cmd_warn",
            decision=decision,
            detail_json={"status": "success"},
        )
    await message.answer(f"已警告用户 {target_user_id}")


@router.message(Command("mute"))
async def mute_command(message: Message, app_context: AppContext) -> None:
    target_user_id = await _target_user(message)
    duration_seconds = _parse_duration_seconds(message.text or "")
    if target_user_id is None or duration_seconds is None:
        await message.answer("用法: /mute <user_id> <10m|1h|1d> 或回复目标消息 /mute 10m")
        return

    chat = message.chat
    actor = message.from_user
    if chat is None or actor is None:
        return

    decision = await _authorize_management_command(
        message=message,
        app_context=app_context,
        action=PermissionAction.MUTE_ANY,
        duration_seconds=duration_seconds,
        target_user_id=target_user_id,
    )
    if decision is None:
        return

    try:
        await moderation.mute_user(message.bot, chat.id, target_user_id, duration_seconds)
    except moderation.ModerationActionError as exc:
        async for session in session_scope(app_context.session_factory):
            await log_management_event(
                session=session,
                chat_id=chat.id,
                actor_user_id=actor.id,
                target_user_id=target_user_id,
                action="cmd_mute",
                decision=decision,
                detail_json={"status": "failed", "error": str(exc), "duration_seconds": duration_seconds},
            )
        await message.answer(f"执行失败: {exc}")
        return

    async for session in session_scope(app_context.session_factory):
        await repositories.create_punishment(
            session=session,
            violation_id=None,
            chat_id=chat.id,
            user_id=target_user_id,
            action="mute",
            duration_seconds=duration_seconds,
            reason="manual_mute",
            executed_by=actor.id,
        )
        await repositories.increment_violation_stats(session, chat.id, target_user_id, "mute")
        await log_management_event(
            session=session,
            chat_id=chat.id,
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            action="cmd_mute",
            decision=decision,
            detail_json={"status": "success", "duration_seconds": duration_seconds},
        )
    await message.answer(f"已禁言用户 {target_user_id} {duration_seconds} 秒")


@router.message(Command("ban"))
async def ban_command(message: Message, app_context: AppContext) -> None:
    target_user_id = await _target_user(message)
    if target_user_id is None:
        await message.answer("用法: /ban <user_id> 或回复目标消息 /ban")
        return

    chat = message.chat
    actor = message.from_user
    if chat is None or actor is None:
        return

    decision = await _authorize_management_command(
        message=message,
        app_context=app_context,
        action=PermissionAction.BAN,
        duration_seconds=None,
        target_user_id=target_user_id,
    )
    if decision is None:
        return

    try:
        await moderation.ban_user(message.bot, chat.id, target_user_id)
    except moderation.ModerationActionError as exc:
        async for session in session_scope(app_context.session_factory):
            await log_management_event(
                session=session,
                chat_id=chat.id,
                actor_user_id=actor.id,
                target_user_id=target_user_id,
                action="cmd_ban",
                decision=decision,
                detail_json={"status": "failed", "error": str(exc)},
            )
        await message.answer(f"执行失败: {exc}")
        return

    async for session in session_scope(app_context.session_factory):
        await repositories.create_punishment(
            session=session,
            violation_id=None,
            chat_id=chat.id,
            user_id=target_user_id,
            action="ban",
            duration_seconds=None,
            reason="manual_ban",
            executed_by=actor.id,
        )
        await repositories.increment_violation_stats(session, chat.id, target_user_id, "ban")
        await log_management_event(
            session=session,
            chat_id=chat.id,
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            action="cmd_ban",
            decision=decision,
            detail_json={"status": "success"},
        )
    await message.answer(f"已封禁用户 {target_user_id}")


@router.message(Command("unban"))
async def unban_command(message: Message, app_context: AppContext) -> None:
    user_id = _parse_user_id_from_text(message.text or "")
    if user_id is None:
        await message.answer("用法: /unban <user_id>")
        return

    chat = message.chat
    actor = message.from_user
    if chat is None or actor is None:
        return

    decision = await _authorize_management_command(
        message=message,
        app_context=app_context,
        action=PermissionAction.UNBAN,
        duration_seconds=None,
        target_user_id=user_id,
    )
    if decision is None:
        return

    try:
        await moderation.unban_user(message.bot, chat.id, user_id)
    except moderation.ModerationActionError as exc:
        async for session in session_scope(app_context.session_factory):
            await log_management_event(
                session=session,
                chat_id=chat.id,
                actor_user_id=actor.id,
                target_user_id=user_id,
                action="cmd_unban",
                decision=decision,
                detail_json={"status": "failed", "error": str(exc)},
            )
        await message.answer(f"执行失败: {exc}")
        return

    async for session in session_scope(app_context.session_factory):
        await repositories.create_punishment(
            session=session,
            violation_id=None,
            chat_id=chat.id,
            user_id=user_id,
            action="unban",
            duration_seconds=None,
            reason="manual_unban",
            executed_by=actor.id,
        )
        await log_management_event(
            session=session,
            chat_id=chat.id,
            actor_user_id=actor.id,
            target_user_id=user_id,
            action="cmd_unban",
            decision=decision,
            detail_json={"status": "success"},
        )
    await message.answer(f"已解封用户 {user_id}")


@router.message(Command("history"))
async def history_command(message: Message, app_context: AppContext) -> None:
    target_user_id = _parse_user_id_from_text(message.text or "")
    if target_user_id is None:
        await message.answer("用法: /history <user_id>")
        return

    chat = message.chat
    actor = message.from_user
    if chat is None or actor is None:
        return

    decision = await _authorize_management_command(
        message=message,
        app_context=app_context,
        action=PermissionAction.VIEW_HISTORY,
        duration_seconds=None,
        target_user_id=target_user_id,
    )
    if decision is None:
        return

    async for session in session_scope(app_context.session_factory):
        rows = await repositories.list_user_history(session, chat.id, target_user_id, 10)
        await log_management_event(
            session=session,
            chat_id=chat.id,
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            action="cmd_history",
            decision=decision,
            detail_json={"status": "success", "count": len(rows)},
        )
        if len(rows) == 0:
            await message.answer("暂无处罚历史")
            return
        lines = [f"{item.created_at} | {item.action} | {item.reason}" for item in rows]
        await message.answer("\n".join(lines))


@router.message(Command("whitelist"))
async def whitelist_command(message: Message, app_context: AppContext) -> None:
    target_user_id = _parse_user_id_from_text(message.text or "")
    if target_user_id is None:
        await message.answer("用法: /whitelist <user_id>")
        return

    chat = message.chat
    actor = message.from_user
    if chat is None or actor is None:
        return

    decision = await _authorize_management_command(
        message=message,
        app_context=app_context,
        action=PermissionAction.WHITELIST,
        duration_seconds=None,
        target_user_id=target_user_id,
    )
    if decision is None:
        return

    async for session in session_scope(app_context.session_factory):
        created = await repositories.add_whitelist_user(session, chat.id, target_user_id)
        await log_management_event(
            session=session,
            chat_id=chat.id,
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            action="cmd_whitelist",
            decision=decision,
            detail_json={"status": "success", "created": created},
        )
    if created:
        await message.answer(f"用户 {target_user_id} 已加入白名单")
        return
    await message.answer("该用户已在白名单")


@router.message(Command("blacklist"))
async def blacklist_command(message: Message, app_context: AppContext) -> None:
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
    actor = message.from_user
    if chat is None or actor is None:
        return

    decision = await _authorize_management_command(
        message=message,
        app_context=app_context,
        action=PermissionAction.BLACKLIST,
        duration_seconds=None,
        target_user_id=target_user_id,
    )
    if decision is None:
        return

    async for session in session_scope(app_context.session_factory):
        created = await repositories.add_blacklist_user(session, chat.id, target_user_id, reason)
        await log_management_event(
            session=session,
            chat_id=chat.id,
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            action="cmd_blacklist",
            decision=decision,
            detail_json={"status": "success", "created": created, "reason": reason},
        )
    if created:
        await message.answer(f"用户 {target_user_id} 已加入黑名单")
        return
    await message.answer("该用户已在黑名单")
