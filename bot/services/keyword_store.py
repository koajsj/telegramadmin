from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from bot.services.keywords import load_keywords_from_directory


@dataclass
class KeywordStore:
    directory_path: Path
    refresh_seconds: int
    _keywords: list[str] | None = None
    _last_loaded_at: float = 0.0

    def get_keywords(self) -> list[str]:
        now = time.time()
        if self._keywords is None:
            self._keywords = load_keywords_from_directory(self.directory_path)
            self._last_loaded_at = now
            return self._keywords

        if now - self._last_loaded_at >= self.refresh_seconds:
            self._keywords = load_keywords_from_directory(self.directory_path)
            self._last_loaded_at = now

        return self._keywords

    def force_reload(self) -> list[str]:
        self._keywords = load_keywords_from_directory(self.directory_path)
        self._last_loaded_at = time.time()
        return self._keywords
