from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleHit:
    rule_name: str
    reason: str
    score: int
    is_link: bool
    is_keyword: bool
    is_flood: bool


@dataclass(frozen=True)
class EnforcementDecision:
    action: str
    duration_seconds: int | None
    reason: str
    level: int
