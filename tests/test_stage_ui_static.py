from __future__ import annotations

import re
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1] / "echobot" / "app" / "web"


class StageUiStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (WEB_ROOT / "stage.html").read_text(encoding="utf-8")
        cls.interaction_js = (
            WEB_ROOT / "features" / "stage" / "interaction.js"
        ).read_text(encoding="utf-8")
        cls.menu_js = (WEB_ROOT / "features" / "stage" / "menu.js").read_text(
            encoding="utf-8",
        )

    def test_stage_menu_is_modal_and_only_final_subtitles_are_announced(self) -> None:
        self.assertRegex(
            self.html,
            r'<aside id="stage-menu-panel"[^>]*role="dialog"[^>]*aria-modal="true"',
        )
        self.assertIn('aria-labelledby="stage-menu-title"', self.html)
        self.assertRegex(
            self.html,
            r'<div id="stage-subtitle-panel" class="stage-subtitle-panel">',
        )
        self.assertNotRegex(
            self.html,
            r'<div id="stage-subtitle-panel"[^>]*aria-live=',
        )
        self.assertRegex(
            self.html,
            r'<p id="stage-announcement"[^>]*role="status"[^>]*aria-live="polite"[^>]*aria-atomic="true"',
        )

        stage_app_js = (WEB_ROOT / "stage-app.js").read_text(encoding="utf-8")
        events_js = (WEB_ROOT / "features" / "stage" / "events.js").read_text(
            encoding="utf-8",
        )
        self.assertIn("function announceSubtitle(value)", stage_app_js)
        delta_handler = events_js.split(
            'source.addEventListener("assistant_delta"',
            1,
        )[1].split('source.addEventListener("subtitle"', 1)[0]
        final_handler = events_js.split(
            'source.addEventListener("assistant_final"',
            1,
        )[1].split('source.addEventListener("character_state"', 1)[0]
        self.assertNotIn("announceSubtitle", delta_handler)
        self.assertIn("announceSubtitle(payload.text)", final_handler)

    def test_pinch_cancels_drag_and_pointer_move_is_ignored_while_pinch_is_active(self) -> None:
        pointer_move = self.interaction_js.split(
            "function handleStagePointerMove(event) {",
            1,
        )[1].split("function handleStagePointerUp", 1)[0]
        self.assertIn("stagePinchActive", pointer_move)
        self.assertIn("cancelStageDrag", self.interaction_js)
        touch_start = self.interaction_js.split(
            "function handleStageTouchStart(event) {",
            1,
        )[1].split("function handleStageTouchMove", 1)[0]
        self.assertIn("cancelStageDrag", touch_start)

    def test_stage_menu_manages_focus_trap_and_underlying_inert_state(self) -> None:
        self.assertIn("stageMenuPreviousFocus", self.menu_js)
        self.assertIn("focusStageMenu", self.menu_js)
        self.assertIn("trapStageMenuFocus", self.menu_js)
        self.assertIn("setStageMenuInert", self.menu_js)
        self.assertIn("inert = open", self.menu_js)
        self.assertIn("menuPanel.contains", self.menu_js)
        self.assertIn("restoreStageMenuFocus", self.menu_js)
        self.assertIn('event.key === "Tab"', self.menu_js)
        self.assertIn("window.setTimeout(() =>", self.menu_js)
        self.assertIn("if (isStageMenuOpen())", self.menu_js)
        self.assertIn("previousFocus !== document.body", self.menu_js)

    def test_long_subtitles_follow_the_latest_visible_line(self) -> None:
        stage_app_js = (WEB_ROOT / "stage-app.js").read_text(encoding="utf-8")
        set_subtitle = stage_app_js.split(
            "function setSubtitle(value) {",
            1,
        )[1].split("\n}\n\nfunction appendSubtitle", 1)[0]

        self.assertIn(
            "subtitleElement.scrollTop = subtitleElement.scrollHeight;",
            set_subtitle,
        )

    def test_invalid_stage_session_is_resolved_before_context_fetch(self) -> None:
        runtime_js = (
            WEB_ROOT / "features" / "stage" / "runtime.js"
        ).read_text(encoding="utf-8")
        api_js = (WEB_ROOT / "features" / "stage" / "api.js").read_text(
            encoding="utf-8",
        )

        self.assertIn("fetchStageSessions", api_js)
        self.assertIn("resolveAvailableSessionName", runtime_js)
        guard_index = runtime_js.index(
            "if (!knownSessionNames.has(requestedSessionName))",
        )
        fetch_index = runtime_js.index(
            "fetchSessionRuntimeContext(requestedSessionName)",
        )
        self.assertLess(guard_index, fetch_index)


if __name__ == "__main__":
    unittest.main()
