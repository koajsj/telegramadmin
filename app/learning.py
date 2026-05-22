from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import re
import time

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

    def _should_skip(self, token: str, current_keywords: set[str]) -> bool:
        if not token:
            return True
        if token in STOPWORDS:
            return True
        if token in current_keywords:
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

    def observe(self, text: str, user_id: int) -> list[str]:
        if not self._store.settings.learning_enabled:
            return []

        now = time.time()
        window = self._store.settings.learning_window_seconds
        min_hits = self._store.settings.learning_min_hits
        min_unique_users = self._store.settings.learning_min_unique_users
        current_keywords = set(self._store.settings.keywords)
        promoted: list[str] = []

        for token in TOKEN_RE.findall(text.lower()):
            token = token.strip(" _-.@")
            if self._should_skip(token, current_keywords):
                continue

            state = self._candidates[token]
            hits, unique_users = state.add(now, user_id, window)

            if hits >= min_hits and unique_users >= min_unique_users:
                if self._store.add_keyword(token):
                    promoted.append(token)
                self._candidates.pop(token, None)

        return promoted
