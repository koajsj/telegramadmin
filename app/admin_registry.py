from __future__ import annotations

import logging
import time

from telegram.error import BadRequest, Forbidden


logger = logging.getLogger("moderation-bot")


class AdminRegistry:
    def __init__(self, refresh_interval_seconds: int = 86400) -> None:
        self._refresh_interval = refresh_interval_seconds
        self._known_chats: set[int] = set()
        self._chat_admins: dict[int, set[int]] = {}
        self._last_refresh: dict[int, float] = {}
        self._admin_ids: set[int] = set()

    def mark_chat(self, chat_id: int) -> None:
        self._known_chats.add(chat_id)

    @property
    def known_chat_count(self) -> int:
        return len(self._known_chats)

    @property
    def admin_count(self) -> int:
        return len(self._admin_ids)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self._admin_ids

    async def refresh_chat(self, bot, chat_id: int, force: bool = False) -> bool:
        now = time.time()
        last = self._last_refresh.get(chat_id, 0.0)
        if not force and now - last < self._refresh_interval:
            return False
        try:
            admins = await bot.get_chat_administrators(chat_id)
        except (BadRequest, Forbidden) as exc:
            logger.warning("Failed to refresh admins for chat %s: %s", chat_id, exc)
            return False
        admin_ids = {admin.user.id for admin in admins}
        self._chat_admins[chat_id] = admin_ids
        self._last_refresh[chat_id] = now
        self._rebuild_admin_ids()
        return True

    async def refresh_known_chats(self, bot) -> int:
        updated = 0
        for chat_id in list(self._known_chats):
            if await self.refresh_chat(bot, chat_id):
                updated += 1
        return updated

    def _rebuild_admin_ids(self) -> None:
        all_admins: set[int] = set()
        for admins in self._chat_admins.values():
            all_admins.update(admins)
        self._admin_ids = all_admins
