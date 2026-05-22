from __future__ import annotations

import os
from types import SimpleNamespace
import unittest


os.environ.setdefault("BOT_TOKEN", "test-token")

from app.rules import RuleEngine, scan_static_reasons  # noqa: E402


def make_settings(**overrides):
    base = dict(
        rule_enable_link=True,
        rule_enable_keywords=True,
        rule_enable_username=True,
        rule_enable_flood=True,
        rule_enable_repeat=True,
        rule_enable_length=True,
        keywords=["casino", "free money", "博彩", "成人视频"],
        max_message_length=600,
        flood_max_messages=2,
        flood_window_seconds=60,
        repeat_max_dupes=2,
        repeat_window_seconds=60,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class ModerationRulesTests(unittest.TestCase):
    def test_username_static_scan_matches_keyword(self) -> None:
        reasons = scan_static_reasons(
            "bestcasino123",
            ["casino"],
            enable_link=True,
            enable_keywords=True,
            enable_length=False,
        )
        self.assertIn("keyword:casino", reasons)

    def test_flood_rule_triggers_after_threshold(self) -> None:
        engine = RuleEngine(make_settings(flood_max_messages=1, flood_window_seconds=60))
        self.assertFalse(engine.evaluate("hello", 1, 100).is_spam)
        self.assertTrue(engine.evaluate("hello again", 1, 100).is_spam)

    def test_keyword_rule_detects_chinese_terms(self) -> None:
        engine = RuleEngine(make_settings())
        result = engine.evaluate("这里有博彩计划群", 1, 100)
        self.assertTrue(result.is_spam)
        self.assertTrue(any(reason.startswith("keyword:") for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
