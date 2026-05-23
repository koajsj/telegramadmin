from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram.types import Message


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_under_watch(joined_at: datetime | None, watch_seconds: int, now: datetime) -> bool:
    if joined_at is None:
        return True
    return now <= joined_at + timedelta(seconds=watch_seconds)


def message_has_link(text: str) -> bool:
    lowered = text.lower()
    return ("http://" in lowered) or ("https://" in lowered) or ("www." in lowered) or ("t.me/" in lowered)


def message_has_media(message: Message) -> bool:
    return any(
        [
            message.photo is not None,
            message.video is not None,
            message.document is not None,
            message.animation is not None,
            message.sticker is not None,
            message.voice is not None,
            message.audio is not None,
        ]
    )


def newcomer_violation_reason(message: Message, text: str, joined_at: datetime | None, watch_seconds: int, allow_links: bool, allow_media: bool) -> str | None:
    now = utc_now()
    if not is_under_watch(joined_at, watch_seconds, now):
        return None
    if (not allow_links) and message_has_link(text):
        return "newcomer_link_blocked"
    if (not allow_media) and message_has_media(message):
        return "newcomer_media_blocked"
    return None
