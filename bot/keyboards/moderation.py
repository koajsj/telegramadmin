from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_log_actions(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="警告（记录违规）", callback_data=f"md:warn:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="禁言10分钟（短期）", callback_data=f"md:mute10:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="禁言1小时（中期）", callback_data=f"md:mute60:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="封禁（高风险）", callback_data=f"md:ban:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="忽略（不处罚）", callback_data=f"md:ignore:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="白名单（后续放行）", callback_data=f"md:wl:{chat_id}:{user_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
