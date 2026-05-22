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
            keywords=["known"],
        )
        self.added: list[str] = []

    def add_keyword(self, keyword: str) -> bool:
        if keyword in self.settings.keywords:
            return False
        self.settings.keywords.append(keyword)
        self.added.append(keyword)
        return True


class AdaptiveLearningTests(unittest.TestCase):
    def test_promotes_repeated_suspicious_token(self) -> None:
        store = FakeStore()
        learner = AdaptiveKeywordLearner(store)

        self.assertEqual(learner.observe("新词推广 123", 1), [])
        self.assertEqual(learner.observe("新词推广 456", 2), [])
        promoted = learner.observe("新词推广 789", 3)

        self.assertIn("新词推广", promoted)
        self.assertIn("新词推广", store.settings.keywords)

    def test_ignores_existing_keywords_and_stopwords(self) -> None:
        store = FakeStore()
        learner = AdaptiveKeywordLearner(store)

        promoted = learner.observe("known 免费 点击 http://example.com", 1)

        self.assertEqual(promoted, [])
        self.assertEqual(store.added, [])


if __name__ == "__main__":
    unittest.main()
