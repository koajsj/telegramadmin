from __future__ import annotations

import re
import time
import unicodedata

from redis.asyncio import Redis

from bot.schemas.moderation import RuleHit


LINK_PATTERN = re.compile(r"(https?://|www\.|t\.me/|telegram\.me/)", re.IGNORECASE)
NON_TOKEN_PATTERN = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")
ZERO_WIDTH_PATTERN = re.compile(r"[\u200b\u200c\u200d\ufeff]")
SPACE_PATTERN = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = ZERO_WIDTH_PATTERN.sub("", normalized)
    normalized = SPACE_PATTERN.sub(" ", normalized.strip().lower())
    return normalized


def compact_text(text: str) -> str:
    return NON_TOKEN_PATTERN.sub("", text.lower())


def contains_link(text: str) -> bool:
    return LINK_PATTERN.search(text) is not None


def contains_keyword(text: str, keywords: list[str]) -> str | None:
    compact = compact_text(text)
    for keyword in keywords:
        normalized_keyword = keyword.strip().lower()
        if normalized_keyword == "":
            continue
        if normalized_keyword in text:
            return normalized_keyword
        if compact_text(normalized_keyword) in compact:
            return normalized_keyword
    return None


async def check_flood(redis_client: Redis, chat_id: int, user_id: int, window_seconds: int, max_messages: int) -> bool:
    now = time.time()
    key = f"flood:{chat_id}:{user_id}"
    min_score = now - float(window_seconds)
    member = f"{now:.6f}-{user_id}"
    await redis_client.zadd(key, {member: now})
    await redis_client.zremrangebyscore(key, 0, min_score)
    count = await redis_client.zcard(key)
    await redis_client.expire(key, window_seconds * 3)
    return int(count) > max_messages


async def evaluate_message(redis_client: Redis, chat_id: int, user_id: int, text: str, keywords: list[str], keyword_score: int, link_score: int, flood_score: int, flood_window_seconds: int, flood_max_messages: int) -> list[RuleHit]:
    normalized = normalize_text(text)
    hits: list[RuleHit] = []

    keyword = contains_keyword(normalized, keywords)
    if keyword is not None:
        hits.append(
            RuleHit(
                rule_name="keyword_blacklist",
                reason=f"keyword:{keyword}",
                score=keyword_score,
                is_link=False,
                is_keyword=True,
                is_flood=False,
            )
        )

    if contains_link(normalized):
        hits.append(
            RuleHit(
                rule_name="link_filter",
                reason="contains_link",
                score=link_score,
                is_link=True,
                is_keyword=False,
                is_flood=False,
            )
        )

    is_flood = await check_flood(redis_client, chat_id, user_id, flood_window_seconds, flood_max_messages)
    if is_flood:
        hits.append(
            RuleHit(
                rule_name="flood_detected",
                reason=f"flood:{flood_max_messages}/{flood_window_seconds}s",
                score=flood_score,
                is_link=False,
                is_keyword=False,
                is_flood=True,
            )
        )

    return hits
