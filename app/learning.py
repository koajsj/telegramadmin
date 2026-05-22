from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import SettingsStore


TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_@.]{3,}")
STOPWORDS = {
    "www",
    "http",
    "https",
    "com",
    "net",
    "org",
    "tme",
    "telegram",
    "telegramme",
    "免费",
    "点击",
    "链接",
    "客服",
    "下载",
    "回复",
    "关注",
    "推广",
    "广告",
    "兼职",
}


@dataclass
class CandidateState:
    records: deque[tuple[float, int]] | None = None

    def __post_init__(self) -> None:
        if self.records is None:
            self.records = deque()

    def add(self, now: float, user_id: int, window: int) -> tuple[int, int]:
        if self.records is None:
            raise RuntimeError("CandidateState.records was not initialized")
        self.records.append((now, user_id))
        while self.records and now - self.records[0][0] > window:
            self.records.popleft()
        hits = len(self.records)
        unique_users = len({item[1] for item in self.records})
        return hits, unique_users


class AdaptiveKeywordLearner:
    def __init__(self, store: SettingsStore) -> None:
        self._store = store
        self._candidates: dict[str, CandidateState] = defaultdict(CandidateState)
        self._benign_candidates: dict[str, CandidateState] = defaultdict(CandidateState)

    def _should_skip(self, token: str) -> bool:
        if not token:
            return True
        if token in STOPWORDS:
            return True
        if token in self._store.settings.keywords:
            return True
        if token in self._store.settings.ignored_keywords:
            return True
        if len(token) > 30:
            return True
        if token.isdigit():
            return True
        if any(ch in token for ch in {".", "@", "/", "\\", ":", "?", "&", "%", "="}):
            return True
        if re.search(r"[a-zA-Z]", token) and not re.fullmatch(r"[a-zA-Z]{3,}", token):
            return True
        return False

    def observe(self, text: str, user_id: int, *, is_spam: bool, score: int) -> list[str]:
        if not self._store.settings.learning_enabled:
            return []

        now = time.time()
        window = self._store.settings.learning_window_seconds
        min_hits = self._store.settings.learning_min_hits
        min_unique_users = self._store.settings.learning_min_unique_users
        promoted: list[str] = []

        for token in TOKEN_RE.findall(text.lower()):
            candidate = token.strip(" _-.@")
            if self._should_skip(candidate):
                continue

            if candidate in self._store.settings.learned_keywords:
                self._store.record_learned_feedback(candidate, is_spam, now)
                continue

            if is_spam and score >= self._store.settings.delete_score_threshold:
                state = self._candidates[candidate]
                hits, unique_users = state.add(now, user_id, window)
                if hits < min_hits or unique_users < min_unique_users:
                    continue

                result = self._store.add_learned_keyword(candidate, hits, unique_users, now)
                promoted.append(candidate)
                self._candidates.pop(candidate, None)
                if result == "promoted":
                    continue
            else:
                benign_state = self._benign_candidates[candidate]
                benign_hits, benign_unique_users = benign_state.add(now, user_id, window)
                if (
                    benign_hits >= self._store.settings.learning_ignore_hits
                    and benign_unique_users >= self._store.settings.learning_ignore_unique_users
                ):
                    self._store.ignore_keyword(candidate)
                    self._benign_candidates.pop(candidate, None)

        return promoted
