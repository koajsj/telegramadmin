from __future__ import annotations


def check_private_owner(chat_type: str, user_id: int, owner_ids: tuple[int, ...]) -> tuple[bool, str]:
    if chat_type != "private":
        return False, "private_only"
    if user_id not in owner_ids:
        return False, "owner_only"
    return True, "ok"
