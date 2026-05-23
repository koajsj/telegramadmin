from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_log_actions(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Delete", callback_data=f"md:del:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="Warn", callback_data=f"md:warn:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="Mute10m", callback_data=f"md:mute10:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="Mute1h", callback_data=f"md:mute60:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="Ban", callback_data=f"md:ban:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="Ignore", callback_data=f"md:ignore:{chat_id}:{user_id}")],
        [InlineKeyboardButton(text="Whitelist", callback_data=f"md:wl:{chat_id}:{user_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
