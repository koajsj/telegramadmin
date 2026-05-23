from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bot.config import Settings


@dataclass(frozen=True)
class AppContext:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    keyword_files_dir: Path
