from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
import unittest


os.environ.setdefault("BOT_TOKEN", "test-token")

from app.rules import RuleEngine, scan_static_reasons  # noqa: E402


def make_settings(overrides: dict[str, Any]) -> SimpleNamespace:
    base: dict[str, Any] = {
        "rule_enable_link": True,
        "rule_enable_keywords": True,
        "rule_enable_username": True,
        "rule_enable_flood": True,
        "rule_enable_repeat": True,
        "rule_enable_length": True,
        "keywords": ["casino", "free money", "博彩", "成人视频"],
        "learned_keywords": ["airdrop"],
        "ignored_keywords": [],
        "max_message_length": 600,
        "flood_max_messages": 2,
        "flood_window_seconds": 60,
        "repeat_max_dupes": 2,
        "repeat_window_seconds": 60,
        "delete_score_threshold": 20,
        "mute_score_threshold": 60,
        "ban_score_threshold": 100,
        "link_score": 35,
        "keyword_score": 60,
        "learned_keyword_score": 18,
        "username_score": 20,
        "length_score": 15,
        "flood_score": 35,
        "repeat_score": 25,
        "structure_score": 12,
        "combo_link_keyword_bonus": 15,
        "combo_username_keyword_bonus": 10,
        "combo_flood_repeat_bonus": 10,
        "combo_structure_link_bonus": 12,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class ModerationRulesTests(unittest.TestCase):
    def test_username_static_scan_matches_keyword(self) -> None:
        reasons = scan_static_reasons(
            "bestcasino123",
            ["casino"],
            learned_keywords=["airdrop"],
            enable_link=True,
            enable_keywords=True,
            enable_length=False,
            max_length=600,
        )
        self.assertIn("keyword:casino", reasons)

    def test_high_keywords_score_more_than_learned_keywords(self) -> None:
        engine = RuleEngine(make_settings({}))
        high = engine.evaluate("这里有博彩计划群", 1, 100)
        learned = engine.evaluate("这里有airdrop", 1, 100)

        self.assertGreater(high.score, learned.score)
        self.assertTrue(high.is_spam)
        self.assertFalse(learned.is_spam)
        self.assertGreater(learned.score, 0)

    def test_flood_rule_triggers_after_threshold(self) -> None:
        engine = RuleEngine(make_settings({"flood_max_messages": 1, "flood_window_seconds": 60}))
        self.assertFalse(engine.evaluate("hello", 1, 100).is_spam)
        self.assertTrue(engine.evaluate("hello again", 1, 100).is_spam)

    def test_structure_hits_raise_score(self) -> None:
        engine = RuleEngine(make_settings({}))
        result = engine.evaluate("私聊我，带链接，返利更高", 1, 100)
        self.assertTrue(result.score >= 12)
        self.assertTrue(any(reason.startswith("structure:") for reason in result.reasons))

    def test_spaced_keyword_bypass_is_normalized(self) -> None:
        engine = RuleEngine(make_settings({}))
        result = engine.evaluate("c a s i n o", 1, 100)
        self.assertTrue(result.is_spam)
        self.assertTrue(any(reason.startswith("keyword:") for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
