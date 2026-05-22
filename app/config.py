from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"
load_dotenv(BASE_DIR / ".env")


def _getenv_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _getenv_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _getenv_list(key: str) -> list[str]:
    value = os.getenv(key, "")
    if not value.strip():
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _getenv_csv(key: str) -> list[str]:
    value = os.getenv(key, "")
    if not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _load_keywords(file_path: Path) -> list[str]:
    if not file_path.exists():
        return []
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = file_path.read_text(encoding="gbk", errors="ignore")
    lines: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line.lower())
    return lines


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _resolve_keyword_files(base_dir: Path) -> list[Path]:
    files: list[Path] = []

    keywords_file = Path(os.getenv("KEYWORDS_FILE", str(DATA_DIR / "keywords.txt")))
    if not keywords_file.is_absolute():
        keywords_file = base_dir / keywords_file
    files.append(keywords_file)

    for item in _getenv_csv("KEYWORDS_FILES"):
        path = Path(item)
        if not path.is_absolute():
            path = base_dir / path
        files.append(path)

    if _getenv_bool("AUTO_LOAD_TXT", True):
        for folder in [DATA_DIR, base_dir]:
            if not folder.exists():
                continue
            for path in folder.glob("*.txt"):
                if path.name.lower() in {"requirements.txt"}:
                    continue
                files.append(path)

    unique: dict[str, Path] = {}
    for path in files:
        key = str(path.resolve()).lower()
        if path.exists():
            unique[key] = path
    return list(unique.values())


def _load_keywords_files(files: list[Path]) -> list[str]:
    keywords: list[str] = []
    for file_path in files:
        keywords.extend(_load_keywords(file_path))
    return keywords


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("state.json must be an object")
    return data


def _save_state(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class Settings:
    bot_token: str
    log_chat_id: int | None
    mute_duration_seconds: int
    action: str
    ban_after_strikes: int
    strike_window_seconds: int
    admin_cache_ttl_seconds: int
    owner_user_ids: list[int]
    keywords: list[str]
    learning_enabled: bool
    learning_min_hits: int
    learning_min_unique_users: int
    learning_window_seconds: int
    rule_enable_link: bool
    rule_enable_keywords: bool
    rule_enable_username: bool
    rule_enable_flood: bool
    rule_enable_repeat: bool
    rule_enable_length: bool
    max_message_length: int
    flood_max_messages: int
    flood_window_seconds: int
    repeat_max_dupes: int
    repeat_window_seconds: int


STATE_KEYS = {
    "mute_duration_seconds",
    "action",
    "ban_after_strikes",
    "rule_enable_link",
    "rule_enable_keywords",
    "rule_enable_username",
    "rule_enable_flood",
    "rule_enable_repeat",
    "rule_enable_length",
    "max_message_length",
    "flood_max_messages",
    "flood_window_seconds",
    "repeat_max_dupes",
    "repeat_window_seconds",
    "learning_enabled",
    "learning_min_hits",
    "learning_min_unique_users",
    "learning_window_seconds",
}


def _apply_state(settings: Settings, state: dict) -> None:
    for key in STATE_KEYS:
        if key in state:
            setattr(settings, key, state[key])


class SettingsStore:
    def __init__(
        self,
        settings: Settings,
        state_path: Path,
        keyword_files: list[Path],
        inline_keywords: list[str],
        custom_keywords: list[str],
        owner_user_ids: list[int],
    ) -> None:
        self._settings = settings
        self._state_path = state_path
        self._keyword_files = keyword_files
        self._inline_keywords = inline_keywords
        self._custom_keywords = custom_keywords
        self._owner_user_ids = owner_user_ids
        self._settings.owner_user_ids = owner_user_ids
        self._last_file_keyword_count = 0
        self.reload_keywords()

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def keyword_files(self) -> list[Path]:
        return self._keyword_files

    @property
    def custom_keywords(self) -> list[str]:
        return self._custom_keywords

    @property
    def owner_user_ids(self) -> list[int]:
        return self._owner_user_ids

    @property
    def last_file_keyword_count(self) -> int:
        return self._last_file_keyword_count

    def is_owner(self, user_id: int) -> bool:
        return user_id in self._owner_user_ids

    def ensure_owner(self, user_id: int) -> bool:
        if self._owner_user_ids:
            return False
        self._owner_user_ids = [user_id]
        self._settings.owner_user_ids = self._owner_user_ids
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self.save_state()
        return True

    def reload_keywords(self) -> int:
        file_keywords = _load_keywords_files(self._keyword_files)
        self._last_file_keyword_count = len(file_keywords)
        combined = self._inline_keywords + self._custom_keywords + file_keywords
        self._settings.keywords = _dedupe(combined)
        return self._last_file_keyword_count

    def add_keyword(self, keyword: str) -> bool:
        normalized = keyword.strip().lower()
        if not normalized:
            return False
        if normalized in self._custom_keywords:
            return False
        self._custom_keywords.append(normalized)
        self.reload_keywords()
        self.save_state()
        return True

    def remove_keyword(self, keyword: str) -> bool:
        normalized = keyword.strip().lower()
        if not normalized or normalized not in self._custom_keywords:
            return False
        self._custom_keywords = [k for k in self._custom_keywords if k != normalized]
        self.reload_keywords()
        self.save_state()
        return True

    def toggle(self, field: str) -> bool:
        current = getattr(self._settings, field)
        new_value = not current
        setattr(self._settings, field, new_value)
        self.save_state()
        return new_value

    def set_action(self, action: str) -> None:
        action = action.strip().lower()
        if action not in {"mute", "ban"}:
            raise ValueError("action must be 'mute' or 'ban'")
        self._settings.action = action
        self.save_state()

    def set_mute_duration(self, seconds: int) -> None:
        if seconds < 0:
            raise ValueError("mute duration must be >= 0")
        self._settings.mute_duration_seconds = seconds
        self.save_state()

    def set_flood_rule(self, max_messages: int, window_seconds: int) -> None:
        if max_messages < 1:
            raise ValueError("flood max messages must be >= 1")
        if window_seconds < 1:
            raise ValueError("flood window must be >= 1")
        self._settings.flood_max_messages = max_messages
        self._settings.flood_window_seconds = window_seconds
        self.save_state()

    def save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {key: getattr(self._settings, key) for key in STATE_KEYS}
        data["custom_keywords"] = self._custom_keywords
        data["owner_user_ids"] = self._owner_user_ids
        _save_state(self._state_path, data)


def load_settings_store() -> SettingsStore:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BOT_TOKEN is required")

    action = os.getenv("ACTION", "mute").strip().lower()
    if action not in {"mute", "ban"}:
        raise ValueError("ACTION must be 'mute' or 'ban'")

    log_chat_id_raw = os.getenv("LOG_CHAT_ID", "").strip()
    log_chat_id = int(log_chat_id_raw) if log_chat_id_raw else None

    state = _load_state(STATE_FILE)
    custom_keywords = [
        str(item).strip().lower()
        for item in state.get("custom_keywords", [])
        if str(item).strip()
    ]
    raw_owner_ids = state.get("owner_user_ids", [])
    owner_user_ids: list[int] = []
    if isinstance(raw_owner_ids, list):
        for item in raw_owner_ids:
            try:
                owner_user_ids.append(int(item))
            except (TypeError, ValueError):
                continue

    settings = Settings(
        bot_token=token,
        log_chat_id=log_chat_id,
        mute_duration_seconds=_getenv_int("MUTE_DURATION_SECONDS", 86400),
        action=action,
        ban_after_strikes=_getenv_int("BAN_AFTER_STRIKES", 0),
        strike_window_seconds=_getenv_int("STRIKE_WINDOW_SECONDS", 86400),
        admin_cache_ttl_seconds=_getenv_int("ADMIN_CACHE_TTL_SECONDS", 300),
        owner_user_ids=owner_user_ids,
        keywords=[],
        rule_enable_link=_getenv_bool("RULE_ENABLE_LINK", True),
        rule_enable_keywords=_getenv_bool("RULE_ENABLE_KEYWORDS", True),
        rule_enable_username=_getenv_bool("RULE_ENABLE_USERNAME", True),
        rule_enable_flood=_getenv_bool("RULE_ENABLE_FLOOD", True),
        rule_enable_repeat=_getenv_bool("RULE_ENABLE_REPEAT", True),
        rule_enable_length=_getenv_bool("RULE_ENABLE_LENGTH", True),
        max_message_length=_getenv_int("MAX_MESSAGE_LENGTH", 600),
        flood_max_messages=_getenv_int("FLOOD_MAX_MESSAGES", 6),
        flood_window_seconds=_getenv_int("FLOOD_WINDOW_SECONDS", 10),
        repeat_max_dupes=_getenv_int("REPEAT_MAX_DUPES", 2),
        repeat_window_seconds=_getenv_int("REPEAT_WINDOW_SECONDS", 60),
        learning_enabled=_getenv_bool("LEARNING_ENABLED", True),
        learning_min_hits=_getenv_int("LEARNING_MIN_HITS", 3),
        learning_min_unique_users=_getenv_int("LEARNING_MIN_UNIQUE_USERS", 2),
        learning_window_seconds=_getenv_int("LEARNING_WINDOW_SECONDS", 86400),
    )

    _apply_state(settings, state)

    keyword_files = _resolve_keyword_files(BASE_DIR)
    inline_keywords = _getenv_list("KEYWORDS")
    return SettingsStore(
        settings,
        STATE_FILE,
        keyword_files,
        inline_keywords,
        custom_keywords,
        owner_user_ids,
    )


settings_store = load_settings_store()
settings = settings_store.settings
