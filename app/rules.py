from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict, deque
import re
import time

from .config import Settings


LINK_RE = re.compile(r"(https?://|www\.|t\.me/)", re.IGNORECASE)


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


@dataclass
class RuleResult:
    is_spam: bool
    reasons: list[str]


class SpamTracker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._flood_times: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self._last_message: dict[tuple[int, int], tuple[str, float, int]] = {}

    def check_flood(self, chat_id: int, user_id: int, now: float) -> bool:
        flood_window = self._settings.flood_window_seconds
        flood_max = self._settings.flood_max_messages
        times = self._flood_times[(chat_id, user_id)]
        times.append(now)
        while times and now - times[0] > flood_window:
            times.popleft()
        return len(times) > flood_max

    def check_repeat(self, chat_id: int, user_id: int, text: str, now: float) -> bool:
        repeat_window = self._settings.repeat_window_seconds
        repeat_max = self._settings.repeat_max_dupes
        key = (chat_id, user_id)
        last_text, last_time, count = self._last_message.get(key, ("", 0.0, 0))
        if text == last_text and now - last_time <= repeat_window:
            count += 1
        else:
            count = 1
        self._last_message[key] = (text, now, count)
        return count > repeat_max


class StrikeTracker:
    def __init__(self, strike_window_seconds: int) -> None:
        self._window = strike_window_seconds
        self._strikes: dict[tuple[int, int], deque[float]] = defaultdict(deque)

    def add_strike(self, chat_id: int, user_id: int, now: float) -> int:
        key = (chat_id, user_id)
        times = self._strikes[key]
        times.append(now)
        while times and now - times[0] > self._window:
            times.popleft()
        return len(times)


class RuleEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tracker = SpamTracker(settings)

    def evaluate(self, text: str, chat_id: int, user_id: int) -> RuleResult:
        now = time.time()
        normalized = _normalize(text)
        reasons: list[str] = []

        if self._settings.rule_enable_link and LINK_RE.search(normalized):
            reasons.append("link")

        if self._settings.rule_enable_keywords and self._settings.keywords:
            for keyword in self._settings.keywords:
                if keyword and keyword in normalized:
                    reasons.append(f"keyword:{keyword}")
                    break

        if self._settings.rule_enable_length and len(normalized) > self._settings.max_message_length:
            reasons.append("length")

        if self._settings.rule_enable_flood:
            if self._tracker.check_flood(chat_id, user_id, now):
                reasons.append("flood")

        if self._settings.rule_enable_repeat:
            if self._tracker.check_repeat(chat_id, user_id, normalized, now):
                reasons.append("repeat")

        return RuleResult(is_spam=bool(reasons), reasons=reasons)


def scan_static_reasons(
    text: str,
    keywords: list[str],
    *,
    enable_link: bool = True,
    enable_keywords: bool = True,
    enable_length: bool = True,
    max_length: int = 600,
) -> list[str]:
    normalized = _normalize(text)
    reasons: list[str] = []

    if enable_link and LINK_RE.search(normalized):
        reasons.append("link")

    if enable_keywords and keywords:
        for keyword in keywords:
            if keyword and keyword in normalized:
                reasons.append(f"keyword:{keyword}")
                break

    if enable_length and len(normalized) > max_length:
        reasons.append("length")

    return reasons
