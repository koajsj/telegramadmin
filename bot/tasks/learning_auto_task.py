from __future__ import annotations

import asyncio
import logging

from bot.app_context import AppContext
from bot.database import repositories
from bot.database.session import session_scope
from bot.services import learning_automation


logger = logging.getLogger(__name__)


async def run_learning_auto_loop(app_context: AppContext) -> None:
    settings = app_context.settings
    interval_seconds = settings.learning_auto_scan_interval_seconds
    while True:
        try:
            async for session in session_scope(app_context.session_factory):
                chat_ids = await repositories.list_all_chat_ids(session)
            for chat_id in chat_ids:
                async for session in session_scope(app_context.session_factory):
                    _ = await learning_automation.run_chat_auto_learning_cycle(
                        session=session,
                        keyword_files_dir=app_context.keyword_files_dir,
                        chat_id=chat_id,
                        days=settings.learning_auto_scan_days,
                        scan_limit=settings.learning_auto_scan_limit,
                        min_confidence=settings.learning_auto_promote_min_confidence,
                        min_evidence=settings.learning_auto_promote_min_evidence,
                        max_false_positive_ratio_percent=settings.learning_auto_promote_max_fp_ratio_percent,
                        promote_limit=120,
                    )
            app_context.keyword_store.force_reload()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "learning_auto_loop_failed",
                extra={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        await asyncio.sleep(interval_seconds)
