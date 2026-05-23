from __future__ import annotations

from aiogram import Router
from aiogram.types import ChatJoinRequest

from bot.app_context import AppContext
from bot.database import repositories
from bot.database.session import session_scope


router = Router(name="join_requests")


@router.chat_join_request()
async def on_join_request(event: ChatJoinRequest, app_context: AppContext) -> None:
    chat = event.chat
    user = event.from_user
    async for session in session_scope(app_context.session_factory):
        await repositories.ensure_chat(
            session=session,
            chat_id=chat.id,
            title=chat.title,
            default_log_chat_id=app_context.settings.default_log_chat_id,
            newcomer_watch_seconds=app_context.settings.newcomer_watch_seconds,
        )
        await repositories.ensure_user(
            session=session,
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            is_bot=user.is_bot,
            language_code=user.language_code,
        )
        await repositories.ensure_chat_member(
            session=session,
            chat_id=chat.id,
            user_id=user.id,
            joined_at=None,
            is_newcomer=True,
        )
        await repositories.create_audit_log(
            session=session,
            chat_id=chat.id,
            actor_user_id=None,
            target_user_id=user.id,
            action="join_request_received",
            detail_json={"bio": getattr(user, "bio", "") or ""},
        )
