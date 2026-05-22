from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Settings


LINK_RE = re.compile(r"(https?://|www\.|t\.me/)", re.IGNORECASE)
ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
SPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    cleaned = ZERO_WIDTH_RE.sub("", text)
    return SPACE_RE.sub(" ", cleaned.strip().lower())


@dataclass
class RuleResult:
    is_spam: bool
    score: int
    reasons: list[str]


class SpamTracker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._flood_times: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self._last_message: dict[tuple[int, int], tuple[str, float, int]] = {}

    def check_flood(self, chat_id: int, user_id: int, now: float) -> bool:
        times = self._flood_times[(chat_id, user_id)]
        times.append(now)
        while times and now - times[0] > self._settings.flood_window_seconds:
            times.popleft()
        return len(times) > self._settings.flood_max_messages

    def check_repeat(self, chat_id: int, user_id: int, text: str, now: float) -> bool:
        key = (chat_id, user_id)
        last_text, last_time, count = self._last_message.get(key, ("", 0.0, 0))
        if text == last_text and now - last_time <= self._settings.repeat_window_seconds:
            count += 1
        else:
            count = 1
        self._last_message[key] = (text, now, count)
        return count > self._settings.repeat_max_dupes


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


def _score_terms(
    normalized: str,
    terms: list[str],
    *,
    prefix: str,
    weight: int,
    ignored: set[str],
) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    matched_terms: list[str] = []
    for term in terms:
        normalized_term = term.strip().lower()
        if not normalized_term or normalized_term in ignored:
            continue
        if normalized_term in normalized:
            score += weight
            reasons.append(f"{prefix}:{normalized_term}")
            matched_terms.append(normalized_term)
            break
    return score, reasons, matched_terms


class RuleEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tracker = SpamTracker(settings)

    def evaluate(self, text: str, chat_id: int, user_id: int, username: str | None = None) -> RuleResult:
        now = time.time()
        normalized = _normalize(text)
        ignored = set(self._settings.ignored_keywords)
        score = 0
        reasons: list[str] = []
        keyword_hit = False
        learned_hit = False
        link_hit = False
        flood_hit = False
        repeat_hit = False

        if self._settings.rule_enable_link and LINK_RE.search(normalized):
            score += self._settings.link_score
            reasons.append("link")
            link_hit = True

        if self._settings.rule_enable_keywords:
            high_score, high_reasons, high_terms = _score_terms(
                normalized,
                self._settings.keywords,
                prefix="keyword",
                weight=self._settings.keyword_score,
                ignored=ignored,
            )
            score += high_score
            reasons.extend(high_reasons)
            keyword_hit = bool(high_terms)

            learned_score, learned_reasons, learned_terms = _score_terms(
                normalized,
                self._settings.learned_keywords,
                prefix="learned",
                weight=self._settings.learned_keyword_score,
                ignored=ignored,
            )
            score += learned_score
            reasons.extend(learned_reasons)
            learned_hit = bool(learned_terms)

        if self._settings.rule_enable_length and len(normalized) > self._settings.max_message_length:
            score += self._settings.length_score
            reasons.append("length")

        if self._settings.rule_enable_flood and self._tracker.check_flood(chat_id, user_id, now):
            score += self._settings.flood_score
            reasons.append("flood")
            flood_hit = True

        if self._settings.rule_enable_repeat and self._tracker.check_repeat(chat_id, user_id, normalized, now):
            score += self._settings.repeat_score
            reasons.append("repeat")
            repeat_hit = True

        if link_hit and keyword_hit:
            score += self._settings.combo_link_keyword_bonus
            reasons.append("combo:link+keyword")

        if username is not None and self._settings.rule_enable_username:
            username_normalized = _normalize(username)
            username_score, username_reasons, _ = _score_terms(
                username_normalized,
                self._settings.keywords + self._settings.learned_keywords,
                prefix="username",
                weight=self._settings.username_score,
                ignored=ignored,
            )
            if LINK_RE.search(username_normalized):
                username_score += self._settings.username_score
                username_reasons.append("username:link")
            if username_score > 0:
                score += username_score
                reasons.extend(username_reasons)
                if keyword_hit or learned_hit:
                    score += self._settings.combo_username_keyword_bonus
                    reasons.append("combo:username+keyword")

        if flood_hit and repeat_hit:
            score += self._settings.combo_flood_repeat_bonus
            reasons.append("combo:flood+repeat")

        return RuleResult(
            is_spam=score >= self._settings.delete_score_threshold,
            score=score,
            reasons=reasons,
        )


def scan_static_reasons(
    text: str,
    keywords: list[str],
    *,
    learned_keywords: list[str] | None = None,
    enable_link: bool = True,
    enable_keywords: bool = True,
    enable_length: bool = True,
    max_length: int = 600,
) -> list[str]:
    normalized = _normalize(text)
    reasons: list[str] = []

    if enable_link and LINK_RE.search(normalized):
        reasons.append("link")

    if enable_keywords:
        for keyword in keywords + (learned_keywords or []):
            normalized_keyword = keyword.strip().lower()
            if normalized_keyword and normalized_keyword in normalized:
                reasons.append(f"keyword:{normalized_keyword}")
                break

    if enable_length and len(normalized) > max_length:
        reasons.append("length")

    return reasons
