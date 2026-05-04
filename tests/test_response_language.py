from __future__ import annotations

import unittest

from echobot.orchestration.response_language import (
    normalize_response_language,
    response_language_instruction,
)


class ResponseLanguageTests(unittest.TestCase):
    def test_normalizes_supported_ui_language_codes(self) -> None:
        self.assertEqual("en", normalize_response_language("en"))
        self.assertEqual("zh-Hant", normalize_response_language("zh-Hant"))
        self.assertEqual("zh-Hant", normalize_response_language("zh-TW"))
        self.assertEqual("zh-Hans", normalize_response_language("zh-Hans"))
        self.assertEqual("zh-Hans", normalize_response_language("zh-CN"))
        self.assertEqual("", normalize_response_language("klingon"))

    def test_instruction_keeps_prompt_language_override(self) -> None:
        instruction = response_language_instruction("zh-Hant")

        self.assertIn("Default response language: Traditional Chinese", instruction)
        self.assertIn("do not reply in Simplified Chinese by default", instruction)
        self.assertIn("explicitly requests another response language", instruction)
