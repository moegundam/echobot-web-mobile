from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "echobot" / "app" / "web"
STAGE_ROOT = WEB_ROOT / "features" / "stage"


class StageModularityTests(unittest.TestCase):
    def test_stage_has_coherent_feature_modules(self) -> None:
        expected_modules = {
            "events.js": "createStageEventController",
            "interaction.js": "createStageInteractionController",
            "live2d.js": "createStageLive2DController",
            "menu.js": "createStageMenuController",
            "runtime.js": "createStageRuntimeController",
            "speech.js": "createStageSpeechController",
        }

        for filename, export_name in expected_modules.items():
            source = (STAGE_ROOT / filename).read_text(encoding="utf-8")
            self.assertRegex(
                source,
                rf"export function {re.escape(export_name)}\(",
                msg=f"{filename} should expose its focused controller",
            )

    def test_stage_entrypoint_is_a_composition_root(self) -> None:
        source = (WEB_ROOT / "stage-app.js").read_text(encoding="utf-8")

        self.assertLess(
            len(source.splitlines()),
            650,
            "Stage behavior should live in focused feature modules",
        )
        for module_name in (
            "events",
            "interaction",
            "live2d",
            "menu",
            "runtime",
            "speech",
        ):
            self.assertRegex(
                source,
                rf'from "\./features/stage/{re.escape(module_name)}\.js(?:\?|\")',
            )

        for private_state in (
            "let audioContext",
            "let stageDragState",
            "let stageMenuPreviousFocus",
            "let live2dModel",
        ):
            self.assertNotIn(private_state, source)

    def test_stage_runtime_refresh_is_revisioned_and_event_driven(self) -> None:
        runtime_source = (STAGE_ROOT / "runtime.js").read_text(encoding="utf-8")
        event_source = (STAGE_ROOT / "events.js").read_text(encoding="utf-8")

        self.assertIn("const STAGE_CONTEXT_REFRESH_INTERVAL_MS = 60000", runtime_source)
        self.assertIn("stageContextRevision", runtime_source)
        self.assertIn("expectedRevision === stageContextRevision", runtime_source)
        self.assertIn('source.addEventListener("runtime_context_changed"', event_source)
        self.assertIn("expectedRevision: payload.revision", event_source)
        self.assertNotIn(
            "void refreshStageContext({ reloadLive2D: true });\n            await playTts",
            event_source,
        )


if __name__ == "__main__":
    unittest.main()
