from __future__ import annotations

from datetime import datetime, timedelta, timezone
import csv
import io
import json

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import repositories


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def export_audit_logs_json(
    session: AsyncSession,
    chat_id: int,
    actor_user_id: int | None,
    action_prefix: str | None,
    days: int,
    limit: int,
) -> bytes:
    since = _utc_now() - timedelta(days=days)
    rows = await repositories.list_audit_logs(
        session=session,
        chat_id=chat_id,
        actor_user_id=actor_user_id,
        action_prefix=action_prefix,
        since=since,
        limit=limit,
    )
    data = [
        {
            "id": item.id,
            "chat_id": item.chat_id,
            "actor_user_id": item.actor_user_id,
            "target_user_id": item.target_user_id,
            "action": item.action,
            "detail": item.detail_json,
            "created_at": item.created_at.isoformat() if item.created_at is not None else None,
        }
        for item in rows
    ]
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


async def export_audit_logs_csv(
    session: AsyncSession,
    chat_id: int,
    actor_user_id: int | None,
    action_prefix: str | None,
    days: int,
    limit: int,
) -> bytes:
    since = _utc_now() - timedelta(days=days)
    rows = await repositories.list_audit_logs(
        session=session,
        chat_id=chat_id,
        actor_user_id=actor_user_id,
        action_prefix=action_prefix,
        since=since,
        limit=limit,
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "chat_id", "actor_user_id", "target_user_id", "action", "created_at", "detail_json"])
    for item in rows:
        writer.writerow(
            [
                item.id,
                item.chat_id,
                item.actor_user_id,
                item.target_user_id,
                item.action,
                item.created_at.isoformat() if item.created_at is not None else "",
                json.dumps(item.detail_json, ensure_ascii=False),
            ]
        )

    return buffer.getvalue().encode("utf-8")
