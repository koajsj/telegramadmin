from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import repositories
from bot.schemas.lexicon import LexiconKind
from bot.services import lexicon_admin


@dataclass(frozen=True)
class CandidateReviewResult:
    candidate_id: int
    status: str
    message: str
    lexicon_entry_id: str | None


def _risk_for_category(category: str) -> str:
    if category in {"scam", "adult_high", "adult_contact", "adult_resource", "domain_blacklist"}:
        return "high"
    return "medium"


def _kind_for_candidate_type(candidate_type: str) -> str:
    if candidate_type == "domain":
        return LexiconKind.DOMAIN.value
    return LexiconKind.WORD.value


async def approve_candidate_to_observe(
    session: AsyncSession,
    keyword_files_dir: Path,
    actor_user_id: int,
    candidate_id: int,
) -> CandidateReviewResult:
    row = await repositories.get_learning_candidate_by_id(session, candidate_id)
    if row is None:
        raise ValueError(f"candidate_not_found:{candidate_id}")
    if row.status == "approved":
        return CandidateReviewResult(
            candidate_id=candidate_id,
            status="approved",
            message="已是正式启用状态",
            lexicon_entry_id=row.lexicon_entry_id,
        )

    entry_id = row.lexicon_entry_id
    if entry_id is None or entry_id == "":
        entry_id = lexicon_admin.add_entry(
            directory_path=keyword_files_dir,
            kind=_kind_for_candidate_type(row.candidate_type),
            category=row.category,
            risk_level=_risk_for_category(row.category),
            value=row.normalized_value,
            source="auto:learning_candidate",
            observe_only=True,
            action_override="log",
            mute_seconds_override=None,
        )
    else:
        _ = lexicon_admin.set_entry_observe_mode(
            directory_path=keyword_files_dir,
            entry_id=entry_id,
            observe_only=True,
            action_override="log",
        )
    updated = await repositories.update_learning_candidate_status(
        session=session,
        candidate_id=candidate_id,
        status="observing",
        actor_user_id=actor_user_id,
        note="owner_or_admin_approved_to_observe",
        lexicon_entry_id=entry_id,
    )
    if updated is None:
        raise ValueError(f"candidate_update_failed:{candidate_id}")
    return CandidateReviewResult(
        candidate_id=candidate_id,
        status="observing",
        message=f"已进入观察模式 entry_id={entry_id}",
        lexicon_entry_id=entry_id,
    )


async def approve_candidate_to_enforce(
    session: AsyncSession,
    keyword_files_dir: Path,
    actor_user_id: int,
    candidate_id: int,
) -> CandidateReviewResult:
    row = await repositories.get_learning_candidate_by_id(session, candidate_id)
    if row is None:
        raise ValueError(f"candidate_not_found:{candidate_id}")
    entry_id = row.lexicon_entry_id
    if entry_id is None or entry_id == "":
        observed = await approve_candidate_to_observe(
            session=session,
            keyword_files_dir=keyword_files_dir,
            actor_user_id=actor_user_id,
            candidate_id=candidate_id,
        )
        entry_id = observed.lexicon_entry_id
    if entry_id is None or entry_id == "":
        raise ValueError(f"lexicon_entry_missing:{candidate_id}")
    changed = lexicon_admin.set_entry_observe_mode(
        directory_path=keyword_files_dir,
        entry_id=entry_id,
        observe_only=False,
        action_override=None,
    )
    if not changed:
        raise ValueError(f"lexicon_entry_not_found:{entry_id}")
    updated = await repositories.update_learning_candidate_status(
        session=session,
        candidate_id=candidate_id,
        status="approved",
        actor_user_id=actor_user_id,
        note="owner_or_admin_approved_to_enforce",
        lexicon_entry_id=entry_id,
    )
    if updated is None:
        raise ValueError(f"candidate_update_failed:{candidate_id}")
    return CandidateReviewResult(
        candidate_id=candidate_id,
        status="approved",
        message=f"已正式启用 entry_id={entry_id}",
        lexicon_entry_id=entry_id,
    )


async def reject_candidate(
    session: AsyncSession,
    actor_user_id: int,
    candidate_id: int,
    reason: str,
) -> CandidateReviewResult:
    updated = await repositories.update_learning_candidate_status(
        session=session,
        candidate_id=candidate_id,
        status="rejected",
        actor_user_id=actor_user_id,
        note=reason,
        lexicon_entry_id=None,
    )
    if updated is None:
        raise ValueError(f"candidate_not_found:{candidate_id}")
    return CandidateReviewResult(
        candidate_id=candidate_id,
        status="rejected",
        message="已拒绝候选词",
        lexicon_entry_id=updated.lexicon_entry_id,
    )
