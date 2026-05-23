from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from bot.services.moderation import decide_escalation
from bot.services.onboarding import is_under_watch, newcomer_violation_reason
from bot.services.rule_engine import evaluate_message


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, list[float]] = {}

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        values = self._store.setdefault(key, [])
        for score in mapping.values():
            values.append(score)

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> None:
        values = self._store.get(key, [])
        self._store[key] = [value for value in values if not (min_score <= value <= max_score)]

    async def zcard(self, key: str) -> int:
        return len(self._store.get(key, []))

    async def expire(self, key: str, seconds: int) -> None:
        _ = (key, seconds)


class FakeMessage:
    def __init__(self, has_photo: bool) -> None:
        self.photo = [object()] if has_photo else None
        self.video = None
        self.document = None
        self.animation = None
        self.sticker = None
        self.voice = None
        self.audio = None


class MvpServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_escalation_steps(self) -> None:
        step1 = decide_escalation(1, 10, 24)
        step3 = decide_escalation(3, 10, 24)
        step5 = decide_escalation(5, 10, 24)

        self.assertEqual(step1.action, "delete")
        self.assertEqual(step3.action, "mute")
        self.assertEqual(step3.duration_seconds, 600)
        self.assertEqual(step5.action, "ban")

    def test_newcomer_watch(self) -> None:
        now = datetime.now(timezone.utc)
        joined = now - timedelta(hours=1)

        self.assertTrue(is_under_watch(joined, 7200, now))
        self.assertFalse(is_under_watch(joined, 600, now))

    def test_newcomer_reason_link(self) -> None:
        now = datetime.now(timezone.utc)
        joined = now - timedelta(minutes=5)
        reason = newcomer_violation_reason(
            message=FakeMessage(False),
            text="visit https://spam.test",
            joined_at=joined,
            watch_seconds=3600,
            allow_links=False,
            allow_media=False,
        )
        self.assertEqual(reason, "newcomer_link_blocked")

    async def test_rule_engine_hits(self) -> None:
        redis = FakeRedis()
        hits = await evaluate_message(
            redis_client=redis,
            chat_id=1,
            user_id=2,
            text="free money https://spam.test",
            keywords=["free money"],
            keyword_score=60,
            link_score=35,
            flood_score=35,
            flood_window_seconds=10,
            flood_max_messages=99,
        )
        reasons = [item.reason for item in hits]
        self.assertIn("keyword:free money", reasons)
        self.assertIn("contains_link", reasons)


if __name__ == "__main__":
    unittest.main()
