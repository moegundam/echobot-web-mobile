from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_documentation.py"
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def test_public_document_index_covers_every_markdown_file() -> None:
    index = ROOT / "docs" / "README.md"
    assert index.is_file()
    targets = {
        target.split("#", 1)[0].removeprefix("./")
        for target in MARKDOWN_LINK.findall(index.read_text(encoding="utf-8"))
        if target and not target.startswith(("http://", "https://", "#"))
    }
    expected = {
        path.relative_to(ROOT / "docs").as_posix()
        for path in (ROOT / "docs").rglob("*.md")
        if path != index
    }
    assert expected <= targets


def test_documentation_validator_accepts_current_public_docs() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--repo-docs",
            "docs",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "broken_links=0" in result.stdout
    assert "unindexed_markdown=0" in result.stdout


def test_documentation_validator_rejects_broken_links(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "README.md").write_text(
        "# Docs\n\n[Missing](./missing.md)\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--repo-docs",
            str(docs),
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "missing.md" in result.stderr
