from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_owner_inventory.py"
OUTPUT_NAMES = {
    "API_OPERATION_INDEX.md",
    "API_SCHEMA_INDEX.md",
    "GENERATED_MANIFEST.md",
    "MODULE_FILE_INDEX.md",
    "TEST_FILE_INDEX.md",
    "ENVIRONMENT_KEY_INDEX.md",
}


def _pydantic_classes() -> set[str]:
    tree = ast.parse((ROOT / "echobot/app/schemas.py").read_text(encoding="utf-8"))
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    pydantic = {"BaseModel"}
    changed = True
    while changed:
        changed = False
        for name, node in classes.items():
            bases = {ast.unparse(base) for base in node.bases}
            if name not in pydantic and bases & pydantic:
                pydantic.add(name)
                changed = True
    return pydantic - {"BaseModel"}


def _test_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(tree)
    )


class OwnerInventoryGeneratorTests(unittest.TestCase):
    def _generate(self, output_dir: Path) -> dict[str, str]:
        subprocess.run(
            [sys.executable, str(SCRIPT), "--output-dir", str(output_dir)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual({path.name for path in output_dir.iterdir()}, OUTPUT_NAMES)
        return {
            name: (output_dir / name).read_text(encoding="utf-8")
            for name in OUTPUT_NAMES
        }

    def test_generation_is_deterministic_complete_and_relative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            first = self._generate(output_dir)
            second = self._generate(output_dir)

        self.assertEqual(first, second)
        combined = "\n".join(first.values())
        self.assertNotIn(str(ROOT), combined)
        self.assertNotIn(str(Path.home()), combined)

        manifest = first["GENERATED_MANIFEST.md"]
        source_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
        self.assertIn(f"Source SHA: **`{source_sha}`**", manifest)
        self.assertIn("Source tree state: **", manifest)
        self.assertIn("Generated at: **", manifest)
        self.assertIn("Generator version: **", manifest)
        self.assertIn(
            "`python scripts/generate_owner_inventory.py --output-dir <owner-docs>/generated`",
            manifest,
        )
        for name in OUTPUT_NAMES - {"GENERATED_MANIFEST.md"}:
            self.assertIn("[Generation Manifest](./GENERATED_MANIFEST.md)", first[name])
            fingerprint = hashlib.sha256(first[name].encode("utf-8")).hexdigest()
            self.assertIn(f"| `{name}` | `{fingerprint}` |", manifest)

        api = first["API_OPERATION_INDEX.md"]
        self.assertIn("`GET` | `/api/web/live2d/{asset_path:path}`", api)
        self.assertIn("`WS` | `/api/web/asr/ws`", api)
        self.assertIn("echobot/app/routers/web.py:107", api)
        self.assertGreaterEqual(api.count("| `GET` |") + api.count("| `POST` |"), 80)

        schema = first["API_SCHEMA_INDEX.md"]
        expected_classes = _pydantic_classes()
        self.assertGreaterEqual(len(expected_classes), 70)
        for class_name in expected_classes:
            self.assertIn(f"`{class_name}`", schema)
        self.assertIn(f"Pydantic classes: **{len(expected_classes)}**", schema)

        modules = first["MODULE_FILE_INDEX.md"]
        python_files = sorted(ROOT.glob("echobot/**/*.py"))
        web_assets = sorted(path for path in (ROOT / "echobot/app/web").rglob("*") if path.is_file())
        self.assertGreaterEqual(len(python_files), 250)
        self.assertGreaterEqual(len(web_assets), 190)
        for path in python_files + web_assets:
            self.assertIn(f"`{path.relative_to(ROOT).as_posix()}`", modules)
        self.assertIn(f"Python modules: **{len(python_files)}**", modules)
        self.assertIn(f"Web assets: **{len(web_assets)}**", modules)

        tests = first["TEST_FILE_INDEX.md"]
        test_files = sorted((ROOT / "tests").glob("test_*.py"))
        self.assertGreaterEqual(len(test_files), 29)
        self.assertIn(
            f"Test functions/methods: **{sum(_test_count(path) for path in test_files)}**",
            tests,
        )
        for path in test_files:
            relative = path.relative_to(ROOT).as_posix()
            self.assertIn(f"`{relative}`", tests)
            self.assertIn(f"| { _test_count(path) } |", tests)
        for name in ("browser_smoke.py", "check_public_safety.py", "live2d_asset_smoke.py"):
            self.assertIn(f"`scripts/{name}`", tests)

    def test_environment_index_lists_tracked_keys_without_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            generated = self._generate(Path(directory))

        environment = generated["ENVIRONMENT_KEY_INDEX.md"]
        tracked_templates = subprocess.check_output(
            ["git", "ls-files", "*.env*.example"],
            cwd=ROOT,
            text=True,
        ).splitlines()
        expected_keys: set[str] = set()
        nonempty_values: set[str] = set()
        for relative in tracked_templates:
            for line in (ROOT / relative).read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.removeprefix("export ").split("=", 1)
                expected_keys.add(key.strip())
                if len(value.strip()) >= 12:
                    nonempty_values.add(value.strip().strip("'\""))

        self.assertGreaterEqual(len(expected_keys), 25)
        for key in expected_keys:
            self.assertIn(f"`{key}`", environment)
        for value in nonempty_values:
            self.assertNotIn(value, environment)
        self.assertIn("secret-looking", environment)
        self.assertIn("non-secret-looking", environment)


if __name__ == "__main__":
    unittest.main()
