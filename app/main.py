from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

from telegram import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .admin_registry import AdminRegistry
from .config import settings, settings_store
from .learning import AdaptiveKeywordLearner
from .rules import RuleEngine, StrikeTracker, scan_static_reasons


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("moderation-bot")


class AdminCache:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._cache: dict[tuple[int, int], tuple[bool, float]] = {}

    async def is_admin(self, bot, chat_id: int, user_id: int) -> bool:
        key = (chat_id, user_id)
        now = time.time()
        cached = self._cache.get(key)
        if cached and cached[1] > now:
            return cached[0]
        member = await bot.get_chat_member(chat_id, user_id)
        is_admin = member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}
        self._cache[key] = (is_admin, now + self._ttl)
        return is_admin


rule_engine = RuleEngine(settings)
strike_tracker = StrikeTracker(settings.strike_window_seconds)
admin_cache = AdminCache(settings.admin_cache_ttl_seconds)
admin_registry = AdminRegistry(refresh_interval_seconds=86400)
learner = AdaptiveKeywordLearner(settings_store)


def _is_private_chat(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.type == "private"


def _is_owner(user_id: int) -> bool:
    return settings_store.is_owner(user_id)


def _is_private_admin(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    return _is_owner(user.id) or admin_registry.is_admin(user.id)


def _format_seconds(seconds: int) -> str:
    if seconds % 86400 == 0 and seconds != 0:
        return f"{seconds // 86400}天"
    if seconds % 3600 == 0 and seconds != 0:
        return f"{seconds // 3600}小时"
    if seconds % 60 == 0 and seconds != 0:
        return f"{seconds // 60}分钟"
    return f"{seconds}秒"


def _flag(value: bool) -> str:
    return "开" if value else "关"


def _status_text(user_id: int | None) -> str:
    action_label = "封禁" if settings.action == "ban" else "禁言"
    keyword_files = len(settings_store.keyword_files)
    custom_keywords = len(settings_store.custom_keywords)
    owner_state = (
        f"已设置: {', '.join(str(item) for item in settings_store.owner_user_ids)}"
        if settings_store.owner_user_ids
        else "未设置"
    )
    user_line = f"你的ID: {user_id}\n" if user_id else ""
    return (
        "✅ 后台管理\n"
        f"{user_line}"
        f"主人: {owner_state}\n"
        f"处理动作: {action_label}\n"
        f"禁言时长: {_format_seconds(settings.mute_duration_seconds)}\n"
        f"关键词数量: {len(settings.keywords)} (文件{keyword_files}个, 自定义{custom_keywords}个)\n"
        f"自学习: {_flag(settings.learning_enabled)}\n"
        f"刷屏规则: {settings.flood_max_messages}条/{settings.flood_window_seconds}秒\n"
        f"规则: 链接{_flag(settings.rule_enable_link)} "
        f"关键词{_flag(settings.rule_enable_keywords)} "
        f"用户名{_flag(settings.rule_enable_username)} "
        f"刷屏{_flag(settings.rule_enable_flood)} "
        f"重复{_flag(settings.rule_enable_repeat)} "
        f"长度{_flag(settings.rule_enable_length)}\n"
        f"管理员同步: {admin_registry.admin_count} (群{admin_registry.known_chat_count}个)\n"
        "指令: /mute 3600 | /action mute|ban | /flood 6 10 | /reloadkeywords | /addkeyword 词 | /delkeyword 词 | /learn"
    )


def _build_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                f"链接检测 {_flag(settings.rule_enable_link)}",
                callback_data="toggle:rule_enable_link",
            ),
            InlineKeyboardButton(
                f"关键词过滤 {_flag(settings.rule_enable_keywords)}",
                callback_data="toggle:rule_enable_keywords",
            ),
        ],
        [
            InlineKeyboardButton(
                f"用户名过滤 {_flag(settings.rule_enable_username)}",
                callback_data="toggle:rule_enable_username",
            ),
        ],
        [
            InlineKeyboardButton(
                f"刷屏拦截 {_flag(settings.rule_enable_flood)}",
                callback_data="toggle:rule_enable_flood",
            ),
            InlineKeyboardButton(
                f"重复消息 {_flag(settings.rule_enable_repeat)}",
                callback_data="toggle:rule_enable_repeat",
            ),
        ],
        [
            InlineKeyboardButton(
                f"超长消息 {_flag(settings.rule_enable_length)}",
                callback_data="toggle:rule_enable_length",
            ),
            InlineKeyboardButton(
                "处理动作 切换为封禁" if settings.action == "mute" else "处理动作 切换为禁言",
                callback_data="action:ban" if settings.action == "mute" else "action:mute",
            ),
        ],
        [
            InlineKeyboardButton(
                f"自学习 {_flag(settings.learning_enabled)}",
                callback_data="toggle:learning_enabled",
            ),
        ],
        [
            InlineKeyboardButton("刷屏 5条/10秒", callback_data="flood:5:10"),
            InlineKeyboardButton("刷屏 8条/10秒", callback_data="flood:8:10"),
            InlineKeyboardButton("刷屏 10条/30秒", callback_data="flood:10:30"),
        ],
        [
            InlineKeyboardButton("禁言 1小时", callback_data="mute:3600"),
            InlineKeyboardButton("禁言 24小时", callback_data="mute:86400"),
            InlineKeyboardButton("禁言 7天", callback_data="mute:604800"),
        ],
        [
            InlineKeyboardButton("重新载入词库", callback_data="reload:keywords"),
            InlineKeyboardButton("刷新状态", callback_data="status"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def _parse_duration(value: str) -> int | None:
    value = value.strip().lower()
    if value.isdigit():
        return int(value)
    match = re.fullmatch(r"(\d+)([smhd])", value)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return amount
    if unit == "m":
        return amount * 60
    if unit == "h":
        return amount * 3600
    if unit == "d":
        return amount * 86400
    return None


async def _reject_private_admin(update: Update) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "未授权。你需要是机器人主人或群管理员。"
        "请在群里发一条消息让机器人同步管理员列表。"
    )


async def _try_claim_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private_chat(update):
        return
    user = update.effective_user
    if user is None:
        return
    if settings_store.owner_user_ids:
        return
    await admin_registry.refresh_known_chats(context.bot)
    if not admin_registry.is_admin(user.id):
        return
    if settings_store.ensure_owner(user.id):
        message = update.effective_message
        if message is not None:
            await message.reply_text("已将你设置为机器人主人（最高权限）。")


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private_chat(update):
        return
    await admin_registry.refresh_known_chats(context.bot)
    await _try_claim_owner(update, context)
    if not _is_private_admin(update):
        await _reject_private_admin(update)
        return
    user_id = update.effective_user.id if update.effective_user else None
    await update.effective_message.reply_text(
        _status_text(user_id),
        reply_markup=_build_keyboard(),
    )


async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private_chat(update):
        return
    await admin_registry.refresh_known_chats(context.bot)
    if not _is_private_admin(update):
        await _reject_private_admin(update)
        return
    user_id = update.effective_user.id if update.effective_user else None
    await update.effective_message.reply_text(
        _status_text(user_id),
        reply_markup=_build_keyboard(),
    )


async def admin_reload_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private_chat(update):
        return
    await admin_registry.refresh_known_chats(context.bot)
    if not _is_private_admin(update):
        await _reject_private_admin(update)
        return
    count = settings_store.reload_keywords()
    await update.effective_message.reply_text(
        f"已重新载入词库，共 {count} 条文件关键词。"
    )


async def admin_set_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private_chat(update):
        return
    await admin_registry.refresh_known_chats(context.bot)
    if not _is_private_admin(update):
        await _reject_private_admin(update)
        return
    if not context.args:
        await update.effective_message.reply_text("用法: /setaction mute 或 /setaction ban")
        return
    try:
        settings_store.set_action(context.args[0])
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return
    await update.effective_message.reply_text(f"处理动作已更新为 {settings.action}")


async def admin_set_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private_chat(update):
        return
    await admin_registry.refresh_known_chats(context.bot)
    if not _is_private_admin(update):
        await _reject_private_admin(update)
        return
    if not context.args:
        await update.effective_message.reply_text("用法: /setmute 3600 或 /setmute 2h")
        return
    duration = _parse_duration(context.args[0])
    if duration is None:
        await update.effective_message.reply_text("无法解析时长，用法: /setmute 3600 或 /setmute 2h")
        return
    settings_store.set_mute_duration(duration)
    await update.effective_message.reply_text(f"禁言时长已更新为 {_format_seconds(duration)}")


async def admin_set_flood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private_chat(update):
        return
    await admin_registry.refresh_known_chats(context.bot)
    if not _is_private_admin(update):
        await _reject_private_admin(update)
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text("用法: /flood 6 10 （6条消息/10秒）")
        return
    try:
        max_messages = int(context.args[0])
        window_seconds = int(context.args[1])
        settings_store.set_flood_rule(max_messages, window_seconds)
    except ValueError as exc:
        await update.effective_message.reply_text(f"参数错误: {exc}")
        return
    await update.effective_message.reply_text(
        f"刷屏规则已更新为 {settings.flood_max_messages}条/{settings.flood_window_seconds}秒"
    )


async def admin_add_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private_chat(update):
        return
    await admin_registry.refresh_known_chats(context.bot)
    if not _is_private_admin(update):
        await _reject_private_admin(update)
        return
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.effective_message.reply_text("用法: /addkeyword 关键词")
        return
    added = settings_store.add_keyword(keyword)
    if added:
        await update.effective_message.reply_text("已添加并生效。")
    else:
        await update.effective_message.reply_text("添加失败（可能已存在或为空）。")


async def admin_del_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private_chat(update):
        return
    await admin_registry.refresh_known_chats(context.bot)
    if not _is_private_admin(update):
        await _reject_private_admin(update)
        return
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.effective_message.reply_text("用法: /delkeyword 关键词")
        return
    removed = settings_store.remove_keyword(keyword)
    if removed:
        await update.effective_message.reply_text("已移除并生效。")
    else:
        await update.effective_message.reply_text("移除失败（仅能移除自定义关键词）。")


async def admin_toggle_learning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private_chat(update):
        return
    await admin_registry.refresh_known_chats(context.bot)
    if not _is_private_admin(update):
        await _reject_private_admin(update)
        return
    new_value = settings_store.toggle("learning_enabled")
    await update.effective_message.reply_text(
        f"自学习功能已{'开启' if new_value else '关闭'}。"
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await admin_registry.refresh_known_chats(context.bot)
    if not _is_private_admin(update):
        await query.answer("无权限", show_alert=True)
        return
    data = query.data or ""
    if data.startswith("toggle:"):
        field = data.split(":", 1)[1]
        if hasattr(settings, field):
            settings_store.toggle(field)
    elif data.startswith("action:"):
        action = data.split(":", 1)[1]
        try:
            settings_store.set_action(action)
        except ValueError:
            await query.answer("动作不合法", show_alert=True)
            return
    elif data.startswith("mute:"):
        try:
            duration = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer("时长不合法", show_alert=True)
            return
        settings_store.set_mute_duration(duration)
    elif data.startswith("flood:"):
        try:
            _, max_messages, window_seconds = data.split(":", 2)
            settings_store.set_flood_rule(int(max_messages), int(window_seconds))
        except ValueError:
            await query.answer("刷屏参数不合法", show_alert=True)
            return
    elif data == "reload:keywords":
        settings_store.reload_keywords()
    elif data == "status":
        pass
    else:
        await query.answer("未知操作", show_alert=True)
        return

    await query.answer()
    user_id = update.effective_user.id if update.effective_user else None
    await query.edit_message_text(_status_text(user_id), reply_markup=_build_keyboard())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if message is None or chat is None or user is None:
        return

    if user.is_bot:
        return

    if chat.type not in {"group", "supergroup"}:
        return

    admin_registry.mark_chat(chat.id)
    await admin_registry.refresh_chat(context.bot, chat.id)

    if _is_owner(user.id):
        return

    if await admin_cache.is_admin(context.bot, chat.id, user.id):
        return

    text = message.text or message.caption
    if not text:
        return

    username = user.username or ""
    result = rule_engine.evaluate(text, chat.id, user.id)
    if settings.rule_enable_username and username:
        username_reasons = scan_static_reasons(
            username,
            settings.keywords,
            enable_link=settings.rule_enable_link,
            enable_keywords=settings.rule_enable_keywords,
            enable_length=False,
        )
        username_reason = next(
            (reason for reason in username_reasons if reason.startswith("keyword:") or reason == "link"),
            None,
        )
        if username_reason and username_reason not in result.reasons:
            result.reasons.append(f"username:{username_reason}")
            result.is_spam = True
    if not result.is_spam:
        return

    try:
        await message.delete()
    except (BadRequest, Forbidden) as exc:
        logger.warning("Failed to delete message in chat %s: %s", chat.id, exc)
        return

    now = datetime.now(timezone.utc)
    if settings.action == "ban":
        try:
            await context.bot.ban_chat_member(chat.id, user.id)
        except (BadRequest, Forbidden) as exc:
            logger.warning("Failed to ban user %s in chat %s: %s", user.id, chat.id, exc)
    elif settings.mute_duration_seconds > 0:
        until = now + timedelta(seconds=settings.mute_duration_seconds)
        permissions = ChatPermissions(can_send_messages=False)
        try:
            await context.bot.restrict_chat_member(
                chat.id,
                user.id,
                permissions=permissions,
                until_date=until,
            )
        except (BadRequest, Forbidden) as exc:
            logger.warning("Failed to mute user %s in chat %s: %s", user.id, chat.id, exc)

    if settings.ban_after_strikes > 0:
        strikes = strike_tracker.add_strike(chat.id, user.id, time.time())
        if strikes >= settings.ban_after_strikes:
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
            except (BadRequest, Forbidden) as exc:
                logger.warning("Failed to ban after strikes for user %s: %s", user.id, exc)

    learned_terms: list[str] = []
    if settings.learning_enabled and not any(reason.startswith("keyword:") for reason in result.reasons):
        learned_terms = learner.observe(text, user.id)

    if settings.log_chat_id:
        reason = ", ".join(result.reasons) if result.reasons else "rule"
        learned = f" Learned: {', '.join(learned_terms)}." if learned_terms else ""
        text_preview = text.replace("\n", " ")[:200]
        log_text = (
            f"Deleted spam in chat {chat.id}. "
            f"User {user.id}. Reasons: {reason}. "
            f"Preview: {text_preview}."
            f"{learned}"
        )
        try:
            await context.bot.send_message(settings.log_chat_id, log_text)
        except (BadRequest, Forbidden) as exc:
            logger.warning("Failed to log to chat %s: %s", settings.log_chat_id, exc)


async def refresh_admins_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await admin_registry.refresh_known_chats(context.bot)


async def post_init(application) -> None:
    commands = [
        BotCommand("start", "打开后台管理"),
        BotCommand("admin", "打开后台管理"),
        BotCommand("status", "查看当前规则状态"),
        BotCommand("reloadkeywords", "重新载入词库"),
        BotCommand("mute", "设置禁言时长"),
        BotCommand("flood", "设置刷屏阈值"),
        BotCommand("action", "设置处理动作"),
        BotCommand("addkeyword", "添加自定义关键词"),
        BotCommand("delkeyword", "删除自定义关键词"),
        BotCommand("learn", "切换自学习功能"),
    ]
    await application.bot.set_my_commands(
        commands,
        scope=BotCommandScopeAllPrivateChats(),
    )


def main() -> None:
    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .post_init(post_init)
        .build()
    )
    application.job_queue.run_repeating(refresh_admins_job, interval=86400, first=60)
    application.add_handler(CommandHandler(["start", "admin"], admin_panel))
    application.add_handler(CommandHandler("status", admin_status))
    application.add_handler(CommandHandler("reloadkeywords", admin_reload_keywords))
    application.add_handler(CommandHandler(["action", "setaction"], admin_set_action))
    application.add_handler(CommandHandler(["mute", "setmute"], admin_set_mute))
    application.add_handler(CommandHandler("flood", admin_set_flood))
    application.add_handler(CommandHandler("addkeyword", admin_add_keyword))
    application.add_handler(CommandHandler("delkeyword", admin_del_keyword))
    application.add_handler(CommandHandler(["learn", "togglelearning"], admin_toggle_learning))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    application.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
