from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import repositories
from bot.schemas.moderation import RuleHit
from bot.services.keywords import normalize_domain, normalize_text
from bot.services.rule_engine import extract_domains


TOKEN_PATTERN = re.compile(r"[0-9a-z\u4e00-\u9fff]{3,32}")
VARIANT_TOKEN_PATTERN = re.compile(r"[0-9a-z@$_\-\.\u4e00-\u9fff]{3,32}")
DEOBFUSCATION_TABLE = str.maketrans(
    {
        "@": "a",
        "$": "s",
        "0": "o",
        "1": "l",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
    }
)


@dataclass(frozen=True)
class CandidateSignal:
    candidate_type: str
    category: str
    normalized_value: str
    sample_value: str | None
    signal: str
    confidence_delta: int
    false_positive_delta: int


@dataclass(frozen=True)
class LearningScanResult:
    scanned_violations: int
    upserted_candidates: int
    pending_candidates: int
    observing_candidates: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_digits_only(value: str) -> bool:
    return all(ch.isdigit() for ch in value)


def _action_weight(action: str) -> int:
    if action == "ban":
        return 24
    if action == "mute":
        return 18
    if action == "warn":
        return 9
    if action == "delete":
        return 12
    if action == "observe":
        return 4
    return 5


def _category_from_hit(hit: RuleHit) -> str:
    category = normalize_text(hit.category)
    if "domain" in category:
        return "domain_blacklist"
    if "adult" in category or "色情" in category:
        return "adult_high"
    if "scam" in category or "诈骗" in category or "博彩" in category:
        return "scam"
    if "flood" in category or "spam" in category:
        return "ad_high"
    return "ad_high"


def _primary_category(hits: list[RuleHit]) -> str:
    if len(hits) == 0:
        return "ad_high"
    ordered = sorted(hits, key=lambda item: item.score, reverse=True)
    return _category_from_hit(ordered[0])


def _normalize_variant(value: str) -> str:
    normalized = normalize_text(value)
    return normalized.translate(DEOBFUSCATION_TABLE)


def _collect_word_signals(text: str, category: str, signal: str, confidence_delta: int) -> list[CandidateSignal]:
    result: list[CandidateSignal] = []
    seen: set[str] = set()
    token_limit = 12
    for raw in TOKEN_PATTERN.findall(normalize_text(text)):
        if len(result) >= token_limit:
            break
        token = normalize_text(raw)
        if token == "" or token in seen:
            continue
        if _is_digits_only(token):
            continue
        if len(token) < 3:
            continue
        seen.add(token)
        result.append(
            CandidateSignal(
                candidate_type="word",
                category=category,
                normalized_value=token,
                sample_value=raw,
                signal=signal,
                confidence_delta=confidence_delta,
                false_positive_delta=0,
            )
        )
    return result


def _collect_variant_signals(text: str, category: str, signal: str, confidence_delta: int) -> list[CandidateSignal]:
    result: list[CandidateSignal] = []
    seen: set[str] = set()
    token_limit = 8
    for raw in VARIANT_TOKEN_PATTERN.findall(text.lower()):
        if len(result) >= token_limit:
            break
        if len(raw) < 3:
            continue
        if all(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in raw):
            continue
        normalized = _normalize_variant(raw)
        if normalized == "" or normalized in seen:
            continue
        if _is_digits_only(normalized):
            continue
        seen.add(normalized)
        result.append(
            CandidateSignal(
                candidate_type="variant_word",
                category=category,
                normalized_value=normalized[:255],
                sample_value=raw[:255],
                signal=signal,
                confidence_delta=confidence_delta,
                false_positive_delta=0,
            )
        )
    return result


def _collect_domain_signals(text: str, signal: str, confidence_delta: int) -> list[CandidateSignal]:
    result: list[CandidateSignal] = []
    seen: set[str] = set()
    token_limit = 6
    for domain in extract_domains(text):
        if len(result) >= token_limit:
            break
        normalized = normalize_domain(domain)
        if normalized == "" or normalized in seen:
            continue
        seen.add(normalized)
        result.append(
            CandidateSignal(
                candidate_type="domain",
                category="domain_blacklist",
                normalized_value=normalized,
                sample_value=domain,
                signal=signal,
                confidence_delta=confidence_delta,
                false_positive_delta=0,
            )
        )
    return result


def _signal_key_from_action(action: str) -> str:
    if action == "":
        return "history_scan"
    return f"action_{action}"


async def observe_from_moderation(
    session: AsyncSession,
    chat_id: int,
    text: str,
    hits: list[RuleHit],
    action_executed: str,
) -> int:
    if len(hits) == 0:
        return 0
    category = _primary_category(hits)
    confidence = _action_weight(action_executed)
    signal = _signal_key_from_action(action_executed)

    combined: list[CandidateSignal] = []
    combined.extend(_collect_word_signals(text, category, signal, confidence))
    combined.extend(_collect_variant_signals(text, category, signal, confidence + 3))
    if any(hit.is_link for hit in hits):
        combined.extend(_collect_domain_signals(text, signal, confidence + 6))

    upserted = 0
    for item in combined:
        await repositories.upsert_learning_candidate(
            session=session,
            chat_id=chat_id,
            candidate_type=item.candidate_type,
            category=item.category,
            normalized_value=item.normalized_value[:255],
            sample_value=item.sample_value,
            signal=item.signal,
            confidence_delta=item.confidence_delta,
            false_positive_delta=item.false_positive_delta,
        )
        upserted += 1
    return upserted


async def scan_history_and_build_suggestions(
    session: AsyncSession,
    chat_id: int,
    days: int,
    limit: int,
) -> LearningScanResult:
    since = _utc_now() - timedelta(days=days)
    violations = await repositories.list_recent_violations(session, chat_id, since, limit)
    false_positive_ids = await repositories.list_false_positive_violation_ids(session, chat_id, since, limit)
    punishment_map = await repositories.list_punishment_actions_by_violation_ids(session, [item.id for item in violations])

    upserted = 0
    for violation in violations:
        excerpt = violation.content_excerpt if violation.content_excerpt is not None else ""
        normalized_reason = normalize_text(violation.reason)
        if excerpt == "":
            continue
        if "domain" in normalized_reason or "link" in normalized_reason:
            domains = _collect_domain_signals(excerpt, "history_scan", 10)
            for item in domains:
                fp_delta = 1 if violation.id in false_positive_ids else 0
                await repositories.upsert_learning_candidate(
                    session=session,
                    chat_id=chat_id,
                    candidate_type=item.candidate_type,
                    category="domain_blacklist",
                    normalized_value=item.normalized_value[:255],
                    sample_value=item.sample_value,
                    signal=item.signal,
                    confidence_delta=item.confidence_delta + _action_weight(punishment_map.get(violation.id, "")),
                    false_positive_delta=fp_delta,
                )
                upserted += 1

        category = "ad_high"
        if "adult" in normalized_reason or "色情" in normalized_reason:
            category = "adult_high"
        elif "scam" in normalized_reason or "诈骗" in normalized_reason or "博彩" in normalized_reason:
            category = "scam"
        confidence = 7 + _action_weight(punishment_map.get(violation.id, ""))
        fp_delta = 1 if violation.id in false_positive_ids else 0
        words = _collect_word_signals(excerpt, category, "history_scan", confidence)
        variants = _collect_variant_signals(excerpt, category, "history_scan", confidence + 2)
        for item in [*words, *variants]:
            await repositories.upsert_learning_candidate(
                session=session,
                chat_id=chat_id,
                candidate_type=item.candidate_type,
                category=item.category,
                normalized_value=item.normalized_value[:255],
                sample_value=item.sample_value,
                signal=item.signal,
                confidence_delta=item.confidence_delta,
                false_positive_delta=fp_delta,
            )
            upserted += 1

    status_count = await repositories.count_learning_candidates_by_status(session, chat_id)
    return LearningScanResult(
        scanned_violations=len(violations),
        upserted_candidates=upserted,
        pending_candidates=int(status_count.get("pending", 0)),
        observing_candidates=int(status_count.get("observing", 0)),
    )
