from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import repositories
from bot.services import learning_intelligence, learning_review


SYSTEM_ACTOR_USER_ID = 0


@dataclass(frozen=True)
class AutoLearningResult:
    chat_id: int
    scanned_violations: int
    upserted_candidates: int
    auto_observing_promotions: int


def _false_positive_ratio_percent(evidence_count: int, false_positive_count: int) -> int:
    if evidence_count <= 0:
        return 100
    return int(false_positive_count * 100 / evidence_count)


async def auto_promote_candidates_to_observing(
    session: AsyncSession,
    keyword_files_dir: Path,
    chat_id: int,
    min_confidence: int,
    min_evidence: int,
    max_false_positive_ratio_percent: int,
    limit: int,
) -> int:
    rows = await repositories.list_learning_candidates(session, chat_id=chat_id, status="pending", limit=limit)
    promoted = 0
    for row in rows:
        evidence_count = int(row.evidence_count)
        false_positive_count = int(row.false_positive_count)
        confidence_score = int(row.confidence_score)
        if evidence_count < min_evidence:
            continue
        if confidence_score < min_confidence:
            continue
        ratio = _false_positive_ratio_percent(evidence_count, false_positive_count)
        if ratio > max_false_positive_ratio_percent:
            continue
        _ = await learning_review.approve_candidate_to_observe(
            session=session,
            keyword_files_dir=keyword_files_dir,
            actor_user_id=SYSTEM_ACTOR_USER_ID,
            candidate_id=int(row.id),
        )
        await repositories.create_audit_log(
            session=session,
            chat_id=chat_id,
            actor_user_id=None,
            target_user_id=None,
            action="learning_candidate_auto_observing",
            detail_json={
                "candidate_id": int(row.id),
                "candidate_type": str(row.candidate_type),
                "normalized_value": str(row.normalized_value),
                "confidence_score": confidence_score,
                "evidence_count": evidence_count,
                "false_positive_count": false_positive_count,
                "false_positive_ratio_percent": ratio,
            },
        )
        promoted += 1
    return promoted


async def run_chat_auto_learning_cycle(
    session: AsyncSession,
    keyword_files_dir: Path,
    chat_id: int,
    days: int,
    scan_limit: int,
    min_confidence: int,
    min_evidence: int,
    max_false_positive_ratio_percent: int,
    promote_limit: int,
) -> AutoLearningResult:
    scan_result = await learning_intelligence.scan_history_and_build_suggestions(
        session=session,
        chat_id=chat_id,
        days=days,
        limit=scan_limit,
    )
    promoted = await auto_promote_candidates_to_observing(
        session=session,
        keyword_files_dir=keyword_files_dir,
        chat_id=chat_id,
        min_confidence=min_confidence,
        min_evidence=min_evidence,
        max_false_positive_ratio_percent=max_false_positive_ratio_percent,
        limit=promote_limit,
    )
    await repositories.create_audit_log(
        session=session,
        chat_id=chat_id,
        actor_user_id=None,
        target_user_id=None,
        action="learning_auto_cycle_completed",
        detail_json={
            "days": days,
            "scan_limit": scan_limit,
            "scanned_violations": scan_result.scanned_violations,
            "upserted_candidates": scan_result.upserted_candidates,
            "auto_observing_promotions": promoted,
        },
    )
    return AutoLearningResult(
        chat_id=chat_id,
        scanned_violations=scan_result.scanned_violations,
        upserted_candidates=scan_result.upserted_candidates,
        auto_observing_promotions=promoted,
    )
