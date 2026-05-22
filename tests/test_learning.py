from __future__ import annotations

import os
from types import SimpleNamespace
import unittest


os.environ.setdefault("BOT_TOKEN", "test-token")

from app.learning import AdaptiveKeywordLearner  # noqa: E402


class FakeStore:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            learning_enabled=True,
            learning_window_seconds=60,
            learning_min_hits=3,
            learning_min_unique_users=2,
            learning_promote_hits=6,
            learning_promote_unique_users=3,
            learning_ignore_hits=4,
            learning_ignore_unique_users=2,
            delete_score_threshold=20,
            keywords=["known"],
            learned_keywords=[],
            ignored_keywords=[],
        )
        self.learned_calls: list[str] = []
        self.promoted_calls: list[str] = []
        self.feedback_calls: list[tuple[str, bool]] = []
        self.ignored_calls: list[str] = []

    def add_learned_keyword(self, keyword: str, hits: int, unique_users: int, now: float) -> str:
        if keyword in self.settings.keywords:
            return "ignored"
        self.learned_calls.append(keyword)
        if keyword not in self.settings.learned_keywords:
            self.settings.learned_keywords.append(keyword)
        if hits >= self.settings.learning_promote_hits and unique_users >= self.settings.learning_promote_unique_users:
            self.promoted_calls.append(keyword)
            if keyword not in self.settings.keywords:
                self.settings.keywords.append(keyword)
            self.settings.learned_keywords = [item for item in self.settings.learned_keywords if item != keyword]
            return "promoted"
        return "learned"

    def record_learned_feedback(self, keyword: str, is_spam: bool, now: float) -> str:
        self.feedback_calls.append((keyword, is_spam))
        if not is_spam:
            self.ignored_calls.append(keyword)
            self.settings.ignored_keywords.append(keyword)
            self.settings.learned_keywords = [item for item in self.settings.learned_keywords if item != keyword]
            return "ignored"
        return "updated"

    def ignore_keyword(self, keyword: str) -> bool:
        if keyword in self.settings.ignored_keywords:
            return False
        self.ignored_calls.append(keyword)
        self.settings.ignored_keywords.append(keyword)
        return True


class AdaptiveLearningTests(unittest.TestCase):
    def test_promotes_repeated_suspicious_token(self) -> None:
        store = FakeStore()
        learner = AdaptiveKeywordLearner(store)

        self.assertEqual(learner.observe("黑产词 123", 1, is_spam=True, score=40), [])
        self.assertEqual(learner.observe("黑产词 456", 2, is_spam=True, score=40), [])
        promoted = learner.observe("黑产词 789", 3, is_spam=True, score=40)

        self.assertIn("黑产词", promoted)
        self.assertIn("黑产词", store.settings.learned_keywords)

    def test_ignores_existing_keywords_and_stopwords(self) -> None:
        store = FakeStore()
        learner = AdaptiveKeywordLearner(store)

        promoted = learner.observe("known 免费 点击 http://example.com", 1, is_spam=False, score=0)

        self.assertEqual(promoted, [])
        self.assertEqual(store.learned_calls, [])
        self.assertEqual(store.feedback_calls, [])

    def test_benign_learned_keyword_can_be_retired(self) -> None:
        store = FakeStore()
        store.settings.learned_keywords = ["sandbox"]
        learner = AdaptiveKeywordLearner(store)

        learner.observe("sandbox", 1, is_spam=False, score=0)

        self.assertEqual(store.feedback_calls, [("sandbox", False)])
        self.assertIn("sandbox", store.ignored_calls)
        self.assertNotIn("sandbox", store.settings.learned_keywords)

    def test_common_clean_token_is_auto_ignored(self) -> None:
        store = FakeStore()
        learner = AdaptiveKeywordLearner(store)

        learner.observe("normalword", 1, is_spam=False, score=0)
        learner.observe("normalword", 2, is_spam=False, score=0)
        learner.observe("normalword", 3, is_spam=False, score=0)
        learner.observe("normalword", 4, is_spam=False, score=0)

        self.assertIn("normalword", store.settings.ignored_keywords)


if __name__ == "__main__":
    unittest.main()
