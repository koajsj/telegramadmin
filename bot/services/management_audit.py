from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import repositories
from bot.schemas.permissions import PermissionDecision


async def log_management_event(
    session: AsyncSession,
    chat_id: int | None,
    actor_user_id: int | None,
    target_user_id: int | None,
    action: str,
    decision: PermissionDecision | None,
    detail_json: dict[str, object],
) -> None:
    detail = dict(detail_json)
    if decision is not None:
        detail["allowed"] = decision.allowed
        detail["role"] = decision.role.value
        detail["reason"] = decision.reason
    await repositories.create_audit_log(
        session=session,
        chat_id=chat_id,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        action=action,
        detail_json=detail,
    )
