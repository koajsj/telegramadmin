from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from aiogram.filters import Command
from aiogram.enums import ChatType
from aiogram.types import BufferedInputFile, Message
from aiogram import Router

from bot.app_context import AppContext
from bot.database import repositories
from bot.database.session import session_scope
from bot.middlewares.owner_guard import check_private_owner
from bot.schemas.lexicon import LexiconKind
from bot.schemas.permissions import PermissionAction, PermissionDecision
from bot.services import audit_export, learning_automation, learning_intelligence, learning_review, lexicon_admin, moderation, statistics
from bot.services.management_audit import log_management_event
from bot.services.keywords import normalize_domain, normalize_text
from bot.services.rule_templates import get_template, template_names
from bot.services.target_guard import ensure_target_action_allowed
from bot.utils.permissions import authorize_action, is_owner


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


def _is_group_chat(message: Message) -> bool:
    chat = message.chat
    if chat is None:
        return False
    return chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}


async def _require_group_chat(message: Message) -> bool:
    if _is_group_chat(message):
        return True
    await message.answer("该命令仅支持在群组中执行。请在目标群内使用。")
    return False


async def _ensure_target_user_exists(
    app_context: AppContext,
    user_id: int,
) -> None:
    async for session in session_scope(app_context.session_factory):
        await repositories.ensure_user(
            session=session,
            user_id=user_id,
            username=None,
            full_name=None,
            is_bot=False,
            language_code=None,
        )


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
        session_factory=app_context.session_factory,
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
        "/reloadkeywords 刷新词库（仅Owner）\n"
        "私聊 Owner 额外命令: /lexicon /template /nightmode /falsepositive /fprules /learn /auditexport /groupstats"
    )
    await message.answer(help_text)


@router.message(Command("settings"))
@router.message(Command("status"))
async def settings_command(message: Message, app_context: AppContext) -> None:
    if not await _require_group_chat(message):
        return

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
    audit_chat_id = chat.id if _is_group_chat(message) else None
    async for session in session_scope(app_context.session_factory):
        await log_management_event(
            session=session,
            chat_id=audit_chat_id,
            actor_user_id=user.id,
            target_user_id=None,
            action="cmd_reload_keywords",
            decision=decision,
            detail_json={"status": "success", "keyword_count": len(keywords)},
        )
    await message.answer(f"词库已刷新，共 {len(keywords)} 个关键词")


@router.message(Command("setlog"))
async def set_log_command(message: Message, app_context: AppContext) -> None:
    if not await _require_group_chat(message):
        return

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
    if not await _require_group_chat(message):
        return

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
    allowed, reason = await ensure_target_action_allowed(
        bot=message.bot,
        settings=app_context.settings,
        session_factory=app_context.session_factory,
        actor_user_id=actor.id,
        chat_id=chat.id,
        target_user_id=target_user_id,
    )
    if not allowed:
        await message.answer(reason)
        return
    await _ensure_target_user_exists(app_context, target_user_id)

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
    if not await _require_group_chat(message):
        return

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
    allowed, reason = await ensure_target_action_allowed(
        bot=message.bot,
        settings=app_context.settings,
        session_factory=app_context.session_factory,
        actor_user_id=actor.id,
        chat_id=chat.id,
        target_user_id=target_user_id,
    )
    if not allowed:
        await message.answer(reason)
        return
    await _ensure_target_user_exists(app_context, target_user_id)

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
    if not await _require_group_chat(message):
        return

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
    allowed, reason = await ensure_target_action_allowed(
        bot=message.bot,
        settings=app_context.settings,
        session_factory=app_context.session_factory,
        actor_user_id=actor.id,
        chat_id=chat.id,
        target_user_id=target_user_id,
    )
    if not allowed:
        await message.answer(reason)
        return
    await _ensure_target_user_exists(app_context, target_user_id)

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
    if not await _require_group_chat(message):
        return

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
    await _ensure_target_user_exists(app_context, user_id)

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
    if not await _require_group_chat(message):
        return

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
    if not await _require_group_chat(message):
        return

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
    if not await _require_group_chat(message):
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


def _parse_command_parts(text: str) -> list[str]:
    return [item.strip() for item in text.strip().split() if item.strip() != ""]


def _parse_positive_int(raw: str) -> int | None:
    try:
        value = int(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


async def _require_private_owner(message: Message, app_context: AppContext) -> bool:
    chat = message.chat
    user = message.from_user
    if chat is None or user is None:
        return False
    allowed, reason = check_private_owner(chat.type, user.id, app_context.settings.owner_ids)
    if not allowed and reason == "private_only":
        await message.answer("该命令仅支持私聊控制台。")
        return False
    if not allowed and reason == "owner_only":
        await message.answer("无权限。")
        return False
    return True


@router.message(Command("lexicon"))
async def lexicon_command(message: Message, app_context: AppContext) -> None:
    if not await _require_private_owner(message, app_context):
        return
    actor = message.from_user
    if actor is None:
        return

    parts = _parse_command_parts(message.text or "")
    if len(parts) <= 1:
        await message.answer(
            "用法:\n"
            "/lexicon stats\n"
            "/lexicon search <query>\n"
            "/lexicon add <kind> <category> <risk> <source> <value>\n"
            "/lexicon del <entry_id>\n"
            "/lexicon enable <entry_id>\n"
            "/lexicon disable <entry_id>\n"
            "/lexicon import <kind> <category> <risk> <source> <v1,v2,v3>\n"
            "/lexicon export"
        )
        return

    action = parts[1].lower()
    if action == "stats":
        snapshot = app_context.keyword_store.get_snapshot()
        words = sum(1 for item in snapshot.entries if item.kind.value == "word")
        domains = sum(1 for item in snapshot.entries if item.kind.value == "domain")
        await message.answer(
            f"词库统计\nentries={len(snapshot.entries)}\nregex_rules={len(snapshot.regex_rules)}\nword_entries={words}\ndomain_entries={domains}\nwhitelist_words={len(snapshot.whitelist_words)}\nwhitelist_domains={len(snapshot.whitelist_domains)}"
        )
        return

    if action == "search":
        if len(parts) < 3:
            await message.answer("用法: /lexicon search <query>")
            return
        query = " ".join(parts[2:])
        rows = lexicon_admin.search_custom_entries(app_context.keyword_files_dir, query)
        if len(rows) == 0:
            await message.answer("未找到词条")
            return
        lines = [
            f"{row.get('entry_id')} | {row.get('kind')} | {row.get('category')} | {row.get('risk_level')} | {'on' if bool(row.get('enabled', True)) else 'off'} | {row.get('value')}"
            for row in rows[:30]
        ]
        await message.answer("\n".join(lines))
        return

    if action == "add":
        if len(parts) < 7:
            await message.answer("用法: /lexicon add <kind> <category> <risk> <source> <value>")
            return
        kind = parts[2]
        category = parts[3]
        risk = parts[4]
        source = parts[5]
        value = " ".join(parts[6:])
        entry_id = lexicon_admin.add_entry(
            directory_path=app_context.keyword_files_dir,
            kind=kind,
            category=category,
            risk_level=risk,
            value=value,
            source=source,
            observe_only=False,
            action_override=None,
            mute_seconds_override=None,
        )
        app_context.keyword_store.force_reload()
        async for session in session_scope(app_context.session_factory):
            await repositories.create_audit_log(
                session=session,
                chat_id=None,
                actor_user_id=actor.id,
                target_user_id=None,
                action="lexicon_rule_adjusted",
                detail_json={"operation": "add", "entry_id": entry_id, "kind": kind, "category": category, "risk": risk},
            )
        await message.answer(f"已添加词条: {entry_id}")
        return

    if action == "del":
        if len(parts) != 3:
            await message.answer("用法: /lexicon del <entry_id>")
            return
        done = lexicon_admin.delete_entry(app_context.keyword_files_dir, parts[2])
        app_context.keyword_store.force_reload()
        async for session in session_scope(app_context.session_factory):
            await repositories.create_audit_log(
                session=session,
                chat_id=None,
                actor_user_id=actor.id,
                target_user_id=None,
                action="lexicon_rule_adjusted",
                detail_json={"operation": "del", "entry_id": parts[2], "changed": done},
            )
        await message.answer("已删除" if done else "未找到词条")
        return

    if action in {"enable", "disable"}:
        if len(parts) != 3:
            await message.answer(f"用法: /lexicon {action} <entry_id>")
            return
        enabled = action == "enable"
        done = lexicon_admin.set_entry_enabled(app_context.keyword_files_dir, parts[2], enabled)
        app_context.keyword_store.force_reload()
        async for session in session_scope(app_context.session_factory):
            await repositories.create_audit_log(
                session=session,
                chat_id=None,
                actor_user_id=actor.id,
                target_user_id=None,
                action="lexicon_rule_adjusted",
                detail_json={"operation": action, "entry_id": parts[2], "changed": done},
            )
        await message.answer("已更新" if done else "未找到词条")
        return

    if action == "import":
        if len(parts) < 7:
            await message.answer("用法: /lexicon import <kind> <category> <risk> <source> <v1,v2,v3>")
            return
        kind = parts[2]
        category = parts[3]
        risk = parts[4]
        source = parts[5]
        values = [item.strip() for item in " ".join(parts[6:]).split(",") if item.strip() != ""]
        count = lexicon_admin.bulk_import(
            directory_path=app_context.keyword_files_dir,
            kind=kind,
            category=category,
            risk_level=risk,
            source=source,
            values=values,
            observe_only=False,
        )
        app_context.keyword_store.force_reload()
        async for session in session_scope(app_context.session_factory):
            await repositories.create_audit_log(
                session=session,
                chat_id=None,
                actor_user_id=actor.id,
                target_user_id=None,
                action="lexicon_rule_adjusted",
                detail_json={"operation": "import", "kind": kind, "category": category, "risk": risk, "count": count},
            )
        await message.answer(f"已导入 {count} 条")
        return

    if action == "export":
        payload = lexicon_admin.export_custom_entries(app_context.keyword_files_dir).encode("utf-8")
        document = BufferedInputFile(payload, filename="custom_lexicon.json")
        async for session in session_scope(app_context.session_factory):
            await repositories.create_audit_log(
                session=session,
                chat_id=None,
                actor_user_id=actor.id,
                target_user_id=None,
                action="lexicon_rule_adjusted",
                detail_json={"operation": "export", "size": len(payload)},
            )
        await message.answer_document(document=document, caption="自定义词库导出")
        return

    await message.answer("不支持的 lexicon 操作")


@router.message(Command("template"))
async def template_command(message: Message, app_context: AppContext) -> None:
    if not await _require_private_owner(message, app_context):
        return
    parts = _parse_command_parts(message.text or "")
    if len(parts) < 2:
        await message.answer(
            "用法:\n"
            "/template list\n"
            "/template preview <chat_id> <template>\n"
            "/template apply <chat_id> <template> confirm"
        )
        return

    sub = parts[1].lower()
    if sub == "list":
        await message.answer("可用模板: " + ", ".join(template_names()))
        return

    if sub == "preview":
        if len(parts) != 4:
            await message.answer("用法: /template preview <chat_id> <template>")
            return
        chat_id = _parse_positive_int(parts[2])
        if chat_id is None:
            await message.answer("chat_id 必须是正整数")
            return
        template = get_template(parts[3])
        if template is None:
            await message.answer("模板不存在")
            return
        async for session in session_scope(app_context.session_factory):
            chat = await repositories.get_chat_settings(session, chat_id)
            if chat is None:
                await message.answer("群组不存在")
                return
            runtime = repositories.get_chat_runtime_settings(chat)
        preview = (
            f"模板预览: {template.name}\n"
            f"newcomer_restrict_enabled: {runtime.get('newcomer_restrict_enabled', chat.newcomer_restrict_enabled)} -> {template.newcomer_restrict_enabled}\n"
            f"keyword_filter_enabled: {chat.keyword_filter_enabled} -> {template.keyword_filter_enabled}\n"
            f"link_filter_enabled: {chat.link_filter_enabled} -> {template.link_filter_enabled}\n"
            f"flood_enabled: {chat.flood_enabled} -> {template.flood_enabled}\n"
            f"enforcement_mode: {runtime.get('enforcement_mode', 'enforce')} -> {template.enforcement_mode}\n"
            f"allow_auto_ban: {runtime.get('allow_auto_ban', False)} -> {template.allow_auto_ban}\n"
            f"确认命令: /template apply {chat_id} {template.name} confirm"
        )
        await message.answer(preview)
        return

    if sub == "apply":
        if len(parts) != 5 or parts[4].lower() != "confirm":
            await message.answer("用法: /template apply <chat_id> <template> confirm")
            return
        chat_id = _parse_positive_int(parts[2])
        if chat_id is None:
            await message.answer("chat_id 必须是正整数")
            return
        template = get_template(parts[3])
        if template is None:
            await message.answer("模板不存在")
            return
        async for session in session_scope(app_context.session_factory):
            chat = await repositories.get_chat_settings(session, chat_id)
            if chat is None:
                await message.answer("群组不存在")
                return
            actor = message.from_user
            if actor is None:
                return
            runtime = repositories.get_chat_runtime_settings(chat)
            await repositories.create_config_snapshot(session, chat_id, actor.id, "before_template_apply", runtime)
            runtime["template_name"] = template.name
            runtime["enforcement_mode"] = template.enforcement_mode
            runtime["allow_auto_ban"] = template.allow_auto_ban
            await repositories.set_chat_runtime_settings(session, chat_id, runtime)
            await repositories.set_chat_switches(
                session=session,
                chat_id=chat_id,
                newcomer_restrict_enabled=template.newcomer_restrict_enabled,
                keyword_filter_enabled=template.keyword_filter_enabled,
                link_filter_enabled=template.link_filter_enabled,
                flood_enabled=template.flood_enabled,
            )
            await repositories.create_audit_log(
                session=session,
                chat_id=chat_id,
                actor_user_id=actor.id,
                target_user_id=None,
                action="template_applied",
                detail_json={"template": template.name},
            )
        await message.answer(f"模板已应用: {template.name}")
        return

    await message.answer("不支持的 template 操作")


@router.message(Command("nightmode"))
async def night_mode_command(message: Message, app_context: AppContext) -> None:
    if not await _require_private_owner(message, app_context):
        return
    parts = _parse_command_parts(message.text or "")
    if len(parts) < 3:
        await message.answer(
            "用法:\n"
            "/nightmode on <chat_id>\n"
            "/nightmode off <chat_id>\n"
            "/nightmode set <chat_id> <timezone> <start_hour> <end_hour>"
        )
        return

    sub = parts[1].lower()
    chat_id = _parse_positive_int(parts[2])
    if chat_id is None:
        await message.answer("chat_id 必须是正整数")
        return
    async for session in session_scope(app_context.session_factory):
        chat = await repositories.get_chat_settings(session, chat_id)
        if chat is None:
            await message.answer("群组不存在")
            return
        runtime = repositories.get_chat_runtime_settings(chat)
        runtime_before_update = deepcopy(runtime)
        night = runtime.get("night_mode")
        if not isinstance(night, dict):
            night = {
                "enabled": False,
                "timezone": "Asia/Shanghai",
                "start_hour": 0,
                "end_hour": 6,
                "flood_window_seconds": 10,
                "flood_max_messages": 3,
                "newcomer_links_blocked": True,
                "newcomer_media_blocked": True,
                "ad_action": "delete",
            }
        if sub == "on":
            night["enabled"] = True
        elif sub == "off":
            night["enabled"] = False
        elif sub == "set":
            if len(parts) != 6:
                await message.answer("用法: /nightmode set <chat_id> <timezone> <start_hour> <end_hour>")
                return
            timezone_name = parts[3]
            try:
                _ = ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError:
                await message.answer("无效时区。示例: Asia/Shanghai")
                return
            try:
                start_hour = int(parts[4])
                end_hour = int(parts[5])
            except ValueError:
                await message.answer("start_hour 和 end_hour 必须是整数")
                return
            if start_hour < 0 or start_hour > 23 or end_hour < 0 or end_hour > 23:
                await message.answer("小时范围必须在 0-23")
                return
            night["timezone"] = timezone_name
            night["start_hour"] = start_hour
            night["end_hour"] = end_hour
        else:
            await message.answer("不支持的 nightmode 操作")
            return
        runtime["night_mode"] = night
        actor = message.from_user
        if actor is None:
            return
        await repositories.create_config_snapshot(
            session,
            chat_id,
            actor.id,
            "before_nightmode_update",
            runtime_before_update,
        )
        await repositories.set_chat_runtime_settings(session, chat_id, runtime)
        await repositories.create_audit_log(
            session=session,
            chat_id=chat_id,
            actor_user_id=actor.id,
            target_user_id=None,
            action="nightmode_updated",
            detail_json={"night_mode": night},
        )
    await message.answer("夜间模式已更新")


@router.message(Command("falsepositive"))
async def false_positive_command(message: Message, app_context: AppContext) -> None:
    if not await _require_private_owner(message, app_context):
        return
    parts = _parse_command_parts(message.text or "")
    if len(parts) < 5:
        await message.answer(
            "用法: /falsepositive <chat_id> <violation_id> <reason> <word:xx|domain:xx|user:123|none> [revoke]"
        )
        return
    chat_id = _parse_positive_int(parts[1])
    violation_id = _parse_positive_int(parts[2])
    if chat_id is None or violation_id is None:
        await message.answer("chat_id 和 violation_id 必须是正整数")
        return
    reason = parts[3]
    action_token = parts[4]
    revoke = len(parts) >= 6 and parts[5].lower() == "revoke"
    actor = message.from_user
    if actor is None:
        return

    async for session in session_scope(app_context.session_factory):
        violation = await repositories.get_violation_by_id(session, violation_id)
        if violation is None or violation.chat_id != chat_id:
            await message.answer("违规记录不存在")
            return
        whitelist_detail: dict[str, object] = {"type": "none"}
        candidate_fp_updates = 0
        if action_token.startswith("word:"):
            word = action_token.split(":", 1)[1]
            entry_id = lexicon_admin.add_entry(
                directory_path=app_context.keyword_files_dir,
                kind=LexiconKind.WORD.value,
                category="word_whitelist",
                risk_level="low",
                value=word,
                source="manual:false_positive",
                observe_only=True,
                action_override="log",
                mute_seconds_override=None,
            )
            whitelist_detail = {"type": "word", "value": word, "entry_id": entry_id}
            candidate_fp_updates = await repositories.mark_learning_candidate_false_positive_by_lexicon_entry(
                session=session,
                chat_id=chat_id,
                lexicon_entry_id=entry_id,
            )
            _ = await repositories.mark_learning_candidate_false_positive_by_key(
                session=session,
                chat_id=chat_id,
                candidate_type=LexiconKind.WORD.value,
                normalized_value=normalize_text(word),
            )
        elif action_token.startswith("domain:"):
            domain = action_token.split(":", 1)[1]
            entry_id = lexicon_admin.add_entry(
                directory_path=app_context.keyword_files_dir,
                kind=LexiconKind.DOMAIN.value,
                category="domain_whitelist",
                risk_level="low",
                value=domain,
                source="manual:false_positive",
                observe_only=True,
                action_override="log",
                mute_seconds_override=None,
            )
            whitelist_detail = {"type": "domain", "value": domain, "entry_id": entry_id}
            candidate_fp_updates = await repositories.mark_learning_candidate_false_positive_by_lexicon_entry(
                session=session,
                chat_id=chat_id,
                lexicon_entry_id=entry_id,
            )
            _ = await repositories.mark_learning_candidate_false_positive_by_key(
                session=session,
                chat_id=chat_id,
                candidate_type=LexiconKind.DOMAIN.value,
                normalized_value=normalize_domain(domain),
            )
        elif action_token.startswith("user:"):
            user_id = _parse_positive_int(action_token.split(":", 1)[1])
            if user_id is None:
                await message.answer("user 白名单参数必须是正整数，例如 user:123456")
                return
            await repositories.add_whitelist_user(session, chat_id, user_id)
            whitelist_detail = {"type": "user", "value": user_id}

        revoked_actions: list[str] = []
        if revoke:
            revoked_actions = await repositories.revoke_punishments_by_violation(
                session=session,
                violation_id=violation_id,
                revoked_by=actor.id,
                revoked_at=datetime.now(timezone.utc),
            )
            for action_name in revoked_actions:
                await repositories.decrement_violation_stats(session, chat_id, violation.user_id, action_name)
        await repositories.create_audit_log(
            session=session,
            chat_id=chat_id,
            actor_user_id=actor.id,
            target_user_id=violation.user_id,
            action="false_positive_marked",
            detail_json={
                "violation_id": violation_id,
                "reason": reason,
                "whitelist": whitelist_detail,
                "revoked_count": len(revoked_actions),
                "candidate_false_positive_updated": candidate_fp_updates,
            },
        )
    app_context.keyword_store.force_reload()
    await message.answer("误判已记录并处理")


@router.message(Command("fprules"))
async def false_positive_rules_command(message: Message, app_context: AppContext) -> None:
    if not await _require_private_owner(message, app_context):
        return
    parts = _parse_command_parts(message.text or "")
    if len(parts) != 2:
        await message.answer("用法: /fprules <chat_id>")
        return
    chat_id = _parse_positive_int(parts[1])
    if chat_id is None:
        await message.answer("chat_id 必须是正整数")
        return
    async for session in session_scope(app_context.session_factory):
        rows = await repositories.top_false_positive_rules(session, chat_id, 10)
    if len(rows) == 0:
        await message.answer("暂无误判统计")
        return
    lines = [f"{item['rule_name']} -> {item['false_positive_count']}" for item in rows]
    await message.answer("\n".join(lines))


def _format_candidate_rows(rows: list[object]) -> str:
    lines: list[str] = []
    for item in rows:
        candidate_id = int(getattr(item, "id"))
        candidate_type = str(getattr(item, "candidate_type"))
        category = str(getattr(item, "category"))
        value = str(getattr(item, "normalized_value"))
        status = str(getattr(item, "status"))
        evidence = int(getattr(item, "evidence_count"))
        confidence = int(getattr(item, "confidence_score"))
        lines.append(
            f"{candidate_id} | {candidate_type} | {category} | {status} | evidence={evidence} | score={confidence} | {value}"
        )
    if len(lines) == 0:
        return "暂无候选建议"
    return "\n".join(lines)


@router.message(Command("learn"))
async def learning_command(message: Message, app_context: AppContext) -> None:
    if not await _require_private_owner(message, app_context):
        return
    actor = message.from_user
    if actor is None:
        return
    parts = _parse_command_parts(message.text or "")
    if len(parts) < 2:
        await message.answer(
            "用法:\n"
            "/learn scan <chat_id> <days> <limit>\n"
            "/learn list <chat_id> <pending|observing|approved|rejected|false_positive|all> <limit>\n"
            "/learn approve <candidate_id> <observe|enable>\n"
            "/learn reject <candidate_id> <reason>\n"
            "/learn stats <chat_id>"
        )
        return

    action = parts[1].lower()
    if action == "scan":
        if len(parts) != 5:
            await message.answer("用法: /learn scan <chat_id> <days> <limit>")
            return
        chat_id = _parse_positive_int(parts[2])
        days = _parse_positive_int(parts[3])
        limit = _parse_positive_int(parts[4])
        if chat_id is None or days is None or limit is None:
            await message.answer("参数必须是正整数")
            return
        async for session in session_scope(app_context.session_factory):
            result = await learning_intelligence.scan_history_and_build_suggestions(
                session=session,
                chat_id=chat_id,
                days=days,
                limit=limit,
            )
            promoted = await learning_automation.auto_promote_candidates_to_observing(
                session=session,
                keyword_files_dir=app_context.keyword_files_dir,
                chat_id=chat_id,
                min_confidence=app_context.settings.learning_auto_promote_min_confidence,
                min_evidence=app_context.settings.learning_auto_promote_min_evidence,
                max_false_positive_ratio_percent=app_context.settings.learning_auto_promote_max_fp_ratio_percent,
                limit=120,
            )
            await repositories.create_audit_log(
                session=session,
                chat_id=chat_id,
                actor_user_id=actor.id,
                target_user_id=None,
                action="learning_suggestion_generated",
                detail_json={
                    "days": days,
                    "limit": limit,
                    "scanned_violations": result.scanned_violations,
                    "upserted_candidates": result.upserted_candidates,
                    "auto_observing_promotions": promoted,
                },
            )
        if promoted > 0:
            app_context.keyword_store.force_reload()
        await message.answer(
            f"学习扫描完成\nscanned={result.scanned_violations}\nupserted={result.upserted_candidates}\nauto_observing={promoted}\npending={result.pending_candidates}\nobserving={result.observing_candidates}"
        )
        return

    if action == "list":
        if len(parts) != 5:
            await message.answer("用法: /learn list <chat_id> <status|all> <limit>")
            return
        chat_id = _parse_positive_int(parts[2])
        status_token = parts[3].lower()
        limit = _parse_positive_int(parts[4])
        if chat_id is None or limit is None:
            await message.answer("参数必须是正整数")
            return
        status = None if status_token == "all" else status_token
        async for session in session_scope(app_context.session_factory):
            rows = await repositories.list_learning_candidates(session, chat_id, status, limit)
        await message.answer(_format_candidate_rows(rows))
        return

    if action == "approve":
        if len(parts) != 4:
            await message.answer("用法: /learn approve <candidate_id> <observe|enable>")
            return
        candidate_id = _parse_positive_int(parts[2])
        approve_mode = parts[3].lower()
        if candidate_id is None or approve_mode not in {"observe", "enable"}:
            await message.answer("参数错误")
            return
        async for session in session_scope(app_context.session_factory):
            if approve_mode == "observe":
                result = await learning_review.approve_candidate_to_observe(
                    session=session,
                    keyword_files_dir=app_context.keyword_files_dir,
                    actor_user_id=actor.id,
                    candidate_id=candidate_id,
                )
            else:
                result = await learning_review.approve_candidate_to_enforce(
                    session=session,
                    keyword_files_dir=app_context.keyword_files_dir,
                    actor_user_id=actor.id,
                    candidate_id=candidate_id,
                )
            await repositories.create_audit_log(
                session=session,
                chat_id=None,
                actor_user_id=actor.id,
                target_user_id=None,
                action="learning_candidate_confirmed",
                detail_json={
                    "candidate_id": candidate_id,
                    "mode": approve_mode,
                    "status": result.status,
                    "lexicon_entry_id": result.lexicon_entry_id,
                },
            )
        app_context.keyword_store.force_reload()
        await message.answer(result.message)
        return

    if action == "reject":
        if len(parts) < 4:
            await message.answer("用法: /learn reject <candidate_id> <reason>")
            return
        candidate_id = _parse_positive_int(parts[2])
        reason = " ".join(parts[3:])
        if candidate_id is None:
            await message.answer("candidate_id 必须是正整数")
            return
        async for session in session_scope(app_context.session_factory):
            result = await learning_review.reject_candidate(
                session=session,
                actor_user_id=actor.id,
                candidate_id=candidate_id,
                reason=reason,
            )
            await repositories.create_audit_log(
                session=session,
                chat_id=None,
                actor_user_id=actor.id,
                target_user_id=None,
                action="learning_candidate_rejected",
                detail_json={"candidate_id": candidate_id, "reason": reason, "status": result.status},
            )
        await message.answer(result.message)
        return

    if action == "stats":
        if len(parts) != 3:
            await message.answer("用法: /learn stats <chat_id>")
            return
        chat_id = _parse_positive_int(parts[2])
        if chat_id is None:
            await message.answer("chat_id 必须是正整数")
            return
        async for session in session_scope(app_context.session_factory):
            status_count = await repositories.count_learning_candidates_by_status(session, chat_id)
        await message.answer(
            "学习候选统计\n"
            f"chat_id={chat_id}\n"
            f"pending={status_count.get('pending', 0)}\n"
            f"observing={status_count.get('observing', 0)}\n"
            f"approved={status_count.get('approved', 0)}\n"
            f"rejected={status_count.get('rejected', 0)}\n"
            f"false_positive={status_count.get('false_positive', 0)}"
        )
        return

    await message.answer("不支持的 learn 操作")


@router.message(Command("auditexport"))
async def audit_export_command(message: Message, app_context: AppContext) -> None:
    if not await _require_private_owner(message, app_context):
        return
    actor = message.from_user
    if actor is None:
        return
    parts = _parse_command_parts(message.text or "")
    if len(parts) != 4:
        await message.answer("用法: /auditexport <chat_id> <json|csv> <days>")
        return
    chat_id = _parse_positive_int(parts[1])
    fmt = parts[2].lower()
    days = _parse_positive_int(parts[3])
    if chat_id is None or days is None or fmt not in {"json", "csv"}:
        await message.answer("参数错误")
        return
    async for session in session_scope(app_context.session_factory):
        if fmt == "json":
            payload = await audit_export.export_audit_logs_json(
                session=session,
                chat_id=chat_id,
                actor_user_id=None,
                action_prefix=None,
                days=days,
                limit=10000,
            )
            filename = f"audit-{chat_id}.json"
        else:
            payload = await audit_export.export_audit_logs_csv(
                session=session,
                chat_id=chat_id,
                actor_user_id=None,
                action_prefix=None,
                days=days,
                limit=10000,
            )
            filename = f"audit-{chat_id}.csv"
        await repositories.create_audit_log(
            session=session,
            chat_id=chat_id,
            actor_user_id=actor.id,
            target_user_id=None,
            action="audit_export_owner",
            detail_json={"format": fmt, "days": days, "size_bytes": len(payload)},
        )
    document = BufferedInputFile(payload, filename=filename)
    await message.answer_document(document=document, caption="审计日志导出")


@router.message(Command("groupstats"))
async def group_stats_command(message: Message, app_context: AppContext) -> None:
    if not await _require_private_owner(message, app_context):
        return
    actor = message.from_user
    if actor is None:
        return
    parts = _parse_command_parts(message.text or "")
    if len(parts) != 3:
        await message.answer("用法: /groupstats <chat_id> <days>")
        return
    chat_id = _parse_positive_int(parts[1])
    days = _parse_positive_int(parts[2])
    if chat_id is None or days is None:
        await message.answer("参数错误")
        return
    async for session in session_scope(app_context.session_factory):
        report = await statistics.build_chat_statistics_report(session, chat_id, days)
        candidate_status = await repositories.count_learning_candidates_by_status(session, chat_id)
        await repositories.create_audit_log(
            session=session,
            chat_id=chat_id,
            actor_user_id=actor.id,
            target_user_id=None,
            action="group_stats_owner",
            detail_json={"days": days},
        )
    tail = (
        "\n\n学习候选状态:\n"
        f"pending={candidate_status.get('pending', 0)} "
        f"observing={candidate_status.get('observing', 0)} "
        f"approved={candidate_status.get('approved', 0)} "
        f"rejected={candidate_status.get('rejected', 0)} "
        f"false_positive={candidate_status.get('false_positive', 0)}"
    )
    await message.answer(report + tail)


@router.message(Command("candidate"))
async def candidate_review_group_command(message: Message, app_context: AppContext) -> None:
    if not await _require_group_chat(message):
        return
    chat = message.chat
    actor = message.from_user
    if chat is None or actor is None:
        return
    parts = _parse_command_parts(message.text or "")
    if len(parts) < 2:
        await message.answer(
            "用法:\n"
            "/candidate list <status|all> <limit>\n"
            "/candidate scan <days> <limit>\n"
            "/candidate approve <candidate_id> <observe|enable>\n"
            "/candidate reject <candidate_id> <reason>"
        )
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
    action = parts[1].lower()
    if action == "list":
        if len(parts) != 4:
            await message.answer("用法: /candidate list <status|all> <limit>")
            return
        status_token = parts[2].lower()
        limit = _parse_positive_int(parts[3])
        if limit is None:
            await message.answer("limit 必须是正整数")
            return
        status = None if status_token == "all" else status_token
        async for session in session_scope(app_context.session_factory):
            rows = await repositories.list_learning_candidates(session, chat.id, status, limit)
            await log_management_event(
                session=session,
                chat_id=chat.id,
                actor_user_id=actor.id,
                target_user_id=None,
                action="candidate_list",
                decision=decision,
                detail_json={"status": status_token, "limit": limit, "result_count": len(rows)},
            )
        await message.answer(_format_candidate_rows(rows))
        return
    if action == "scan":
        if len(parts) != 4:
            await message.answer("用法: /candidate scan <days> <limit>")
            return
        days = _parse_positive_int(parts[2])
        limit = _parse_positive_int(parts[3])
        if days is None or limit is None:
            await message.answer("参数错误")
            return
        async for session in session_scope(app_context.session_factory):
            result = await learning_intelligence.scan_history_and_build_suggestions(session, chat.id, days, limit)
            promoted = await learning_automation.auto_promote_candidates_to_observing(
                session=session,
                keyword_files_dir=app_context.keyword_files_dir,
                chat_id=chat.id,
                min_confidence=app_context.settings.learning_auto_promote_min_confidence,
                min_evidence=app_context.settings.learning_auto_promote_min_evidence,
                max_false_positive_ratio_percent=app_context.settings.learning_auto_promote_max_fp_ratio_percent,
                limit=120,
            )
            await log_management_event(
                session=session,
                chat_id=chat.id,
                actor_user_id=actor.id,
                target_user_id=None,
                action="candidate_scan",
                decision=decision,
                detail_json={
                    "days": days,
                    "limit": limit,
                    "scanned_violations": result.scanned_violations,
                    "upserted_candidates": result.upserted_candidates,
                    "auto_observing_promotions": promoted,
                },
            )
        if promoted > 0:
            app_context.keyword_store.force_reload()
        await message.answer(f"学习扫描完成: scanned={result.scanned_violations} upserted={result.upserted_candidates} auto_observing={promoted}")
        return
    if action == "approve":
        if len(parts) != 4:
            await message.answer("用法: /candidate approve <candidate_id> <observe|enable>")
            return
        candidate_id = _parse_positive_int(parts[2])
        mode = parts[3].lower()
        if candidate_id is None or mode not in {"observe", "enable"}:
            await message.answer("参数错误")
            return
        async for session in session_scope(app_context.session_factory):
            row = await repositories.get_learning_candidate_by_id(session, candidate_id)
            if row is None or row.chat_id != chat.id:
                await message.answer("候选词不存在或不属于本群")
                return
            if mode == "observe":
                result = await learning_review.approve_candidate_to_observe(
                    session=session,
                    keyword_files_dir=app_context.keyword_files_dir,
                    actor_user_id=actor.id,
                    candidate_id=candidate_id,
                )
            else:
                result = await learning_review.approve_candidate_to_enforce(
                    session=session,
                    keyword_files_dir=app_context.keyword_files_dir,
                    actor_user_id=actor.id,
                    candidate_id=candidate_id,
                )
            await log_management_event(
                session=session,
                chat_id=chat.id,
                actor_user_id=actor.id,
                target_user_id=None,
                action="candidate_approve",
                decision=decision,
                detail_json={"candidate_id": candidate_id, "mode": mode, "status": result.status},
            )
        app_context.keyword_store.force_reload()
        await message.answer(result.message)
        return
    if action == "reject":
        if len(parts) < 4:
            await message.answer("用法: /candidate reject <candidate_id> <reason>")
            return
        candidate_id = _parse_positive_int(parts[2])
        reason = " ".join(parts[3:])
        if candidate_id is None:
            await message.answer("candidate_id 必须是正整数")
            return
        async for session in session_scope(app_context.session_factory):
            row = await repositories.get_learning_candidate_by_id(session, candidate_id)
            if row is None or row.chat_id != chat.id:
                await message.answer("候选词不存在或不属于本群")
                return
            result = await learning_review.reject_candidate(session, actor.id, candidate_id, reason)
            await log_management_event(
                session=session,
                chat_id=chat.id,
                actor_user_id=actor.id,
                target_user_id=None,
                action="candidate_reject",
                decision=decision,
                detail_json={"candidate_id": candidate_id, "reason": reason, "status": result.status},
            )
        await message.answer(result.message)
        return

    await message.answer("不支持的 candidate 操作")



