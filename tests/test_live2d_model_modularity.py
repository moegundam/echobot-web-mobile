from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "echobot" / "app" / "web"


def run_node_module(script: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


class Live2DModelModularityTests(unittest.TestCase):
    def test_transform_helpers_preserve_existing_viewport_behavior(self) -> None:
        result = run_node_module(
            f'''
import fs from "node:fs";
const transform = await import("data:text/javascript," + encodeURIComponent(fs.readFileSync({str(WEB_ROOT / "features" / "live2d" / "model" / "transform.js")!r}, "utf8")));
const {{
    calculateDefaultTransform,
    calculateResizedTransform,
    canRestoreSavedTransform,
    normalizeSelectionKey,
    selectionKeyFromConfig,
}} = transform;

console.log(JSON.stringify({{
    selection: normalizeSelectionKey("  demo  "),
    configured: selectionKeyFromConfig({{ selection_key: "  profile-a  ", model_url: "/fallback.model3.json" }}),
    fallback: selectionKeyFromConfig({{ model_url: "/fallback.model3.json" }}),
    defaultTransform: calculateDefaultTransform({{
        stageWidth: 1000,
        stageHeight: 800,
        baseSize: {{ width: 500, height: 1000 }},
    }}),
    resized: calculateResizedTransform({{
        modelX: 500,
        modelY: 400,
        modelScale: 1,
        previousStageSize: {{ width: 1000, height: 800 }},
        currentStageSize: {{ width: 500, height: 400 }},
    }}),
    restoreNear: canRestoreSavedTransform(
        {{ stageWidth: 1000, stageHeight: 800 }},
        {{ width: 900, height: 700 }},
    ),
    restoreFar: canRestoreSavedTransform(
        {{ stageWidth: 1000, stageHeight: 800 }},
        {{ width: 400, height: 400 }},
    ),
}}));
''',
        )

        self.assertEqual("demo", result["selection"])
        self.assertEqual("profile-a", result["configured"])
        self.assertEqual("/fallback.model3.json", result["fallback"])
        self.assertEqual({"x": 500, "y": 496, "scale": 0.656}, result["defaultTransform"])
        self.assertEqual({"x": 250, "y": 200, "scale": 0.5}, result["resized"])
        self.assertTrue(result["restoreNear"])
        self.assertFalse(result["restoreFar"])

    def test_expression_helpers_preserve_input_normalization(self) -> None:
        result = run_node_module(
            f'''
import fs from "node:fs";
const expressions = await import("data:text/javascript," + encodeURIComponent(fs.readFileSync({str(WEB_ROOT / "features" / "live2d" / "model" / "expressions.js")!r}, "utf8")));
const {{
    normalizeExpressionBlend,
    normalizeExpressionItem,
    normalizeHotkeyItem,
    normalizeMotionItem,
    parseExpressionDefinition,
}} = expressions;

console.log(JSON.stringify({{
    expression: normalizeExpressionItem({{ file: "smile.exp3.json", url: "/smile", name: "" }}),
    motion: normalizeMotionItem({{ file: "idle.motion3.json", group: "Idle", index: 2, name: "" }}),
    hotkey: normalizeHotkeyItem({{ action: "ToggleExpression", file: "smile.exp3.json", supported: 1 }}),
    add: normalizeExpressionBlend(" add "),
    multiply: normalizeExpressionBlend("MULTIPLY"),
    set: normalizeExpressionBlend("unknown"),
    definition: parseExpressionDefinition(
        {{ Parameters: [
            {{ Id: "ParamMouth", Value: 0.8, Blend: "Add" }},
            {{ Id: "ParamAngle", Value: -0.2, Blend: "multiply" }},
            {{ Id: "", Value: 1 }},
        ] }},
        {{ name: "Smile", file: "smile.exp3.json" }},
    ),
}}));
''',
        )

        self.assertEqual(
            {"name": "smile.exp3.json", "file": "smile.exp3.json", "url": "/smile"},
            result["expression"],
        )
        self.assertEqual(
            {"name": "idle.motion3.json", "file": "idle.motion3.json", "group": "Idle", "index": 2},
            result["motion"],
        )
        self.assertEqual(
            {
                "hotkey_id": "",
                "name": "ToggleExpression",
                "action": "ToggleExpression",
                "file": "smile.exp3.json",
                "supported": True,
            },
            result["hotkey"],
        )
        self.assertEqual("Add", result["add"])
        self.assertEqual("Multiply", result["multiply"])
        self.assertEqual("Set", result["set"])
        self.assertEqual(
            {
                "name": "Smile",
                "file": "smile.exp3.json",
                "parameters": [
                    {"id": "ParamMouth", "value": 0.8, "blend": "Add"},
                    {"id": "ParamAngle", "value": -0.2, "blend": "Multiply"},
                ],
            },
            result["definition"],
        )

    def test_facade_keeps_public_factory_and_is_materially_smaller(self) -> None:
        facade = (WEB_ROOT / "features" / "live2d" / "model.js").read_text(encoding="utf-8")
        facade_lines = len(facade.splitlines())

        self.assertIn("export function createLive2DModelController(deps)", facade)
        self.assertIn("createLive2DExpressionController", facade)
        self.assertIn("createLive2DFocusController", facade)
        self.assertIn("calculateResizedTransform", facade)
        self.assertLess(facade_lines, 700, f"facade remains too large: {facade_lines} lines")

        for module_name in ("transform.js", "focus.js", "expressions.js"):
            module = WEB_ROOT / "features" / "live2d" / "model" / module_name
            self.assertTrue(module.exists(), module_name)
            self.assertGreater(len(module.read_text(encoding="utf-8").splitlines()), 20)


if __name__ == "__main__":
    unittest.main()
