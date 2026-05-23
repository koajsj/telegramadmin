from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class SettingsError(ValueError):
    """Raised when required settings are missing or invalid."""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    redis_url: str
    log_level: str
    admin_ids: tuple[int, ...]
    default_log_chat_id: int | None
    environment: str
    webhook_url: str | None
    webhook_secret: str | None
    newcomer_watch_seconds: int
    newcomer_allow_links: bool
    newcomer_allow_media: bool
    flood_window_seconds: int
    flood_max_messages: int
    mute_minutes_step3: int
    mute_hours_step4: int


def _read_text(key: str) -> str:
    value = os.getenv(key, "").strip()
    if value == "":
        raise SettingsError(f"Missing required environment variable: {key}")
    return value


def _read_optional_text(key: str) -> str | None:
    value = os.getenv(key, "").strip()
    if value == "":
        return None
    return value


def _read_int(key: str, fallback: int) -> int:
    raw = os.getenv(key, "").strip()
    if raw == "":
        return fallback
    try:
        return int(raw)
    except ValueError as exc:
        raise SettingsError(f"Invalid integer for {key}: {raw}") from exc


def _read_bool(key: str, fallback: bool) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if raw == "":
        return fallback
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    raise SettingsError(f"Invalid boolean for {key}: {raw}")


def _read_admin_ids(key: str) -> tuple[int, ...]:
    raw = os.getenv(key, "").strip()
    if raw == "":
        return tuple()
    parts = [item.strip() for item in raw.split(",") if item.strip()]
    result: list[int] = []
    for part in parts:
        try:
            result.append(int(part))
        except ValueError as exc:
            raise SettingsError(f"Invalid admin id in {key}: {part}") from exc
    return tuple(result)


def load_settings() -> Settings:
    log_chat_raw = _read_optional_text("DEFAULT_LOG_CHAT_ID")
    default_log_chat_id = int(log_chat_raw) if log_chat_raw is not None else None

    return Settings(
        bot_token=_read_text("BOT_TOKEN"),
        database_url=_read_text("DATABASE_URL"),
        redis_url=_read_text("REDIS_URL"),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        admin_ids=_read_admin_ids("ADMIN_IDS"),
        default_log_chat_id=default_log_chat_id,
        environment=os.getenv("ENVIRONMENT", "development").strip().lower() or "development",
        webhook_url=_read_optional_text("WEBHOOK_URL"),
        webhook_secret=_read_optional_text("WEBHOOK_SECRET"),
        newcomer_watch_seconds=_read_int("NEWCOMER_WATCH_SECONDS", 86400),
        newcomer_allow_links=_read_bool("NEWCOMER_ALLOW_LINKS", False),
        newcomer_allow_media=_read_bool("NEWCOMER_ALLOW_MEDIA", False),
        flood_window_seconds=_read_int("FLOOD_WINDOW_SECONDS", 10),
        flood_max_messages=_read_int("FLOOD_MAX_MESSAGES", 5),
        mute_minutes_step3=_read_int("MUTE_MINUTES_STEP3", 10),
        mute_hours_step4=_read_int("MUTE_HOURS_STEP4", 24),
    )
