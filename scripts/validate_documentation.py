from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
MANIFEST_ROW = re.compile(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$")
EXTERNAL_PREFIXES = (
    "http://",
    "https://",
    "mailto:",
    "data:",
)


@dataclass(slots=True)
class DocumentationReport:
    markdown_files: int = 0
    local_links: int = 0
    broken_links: list[str] = field(default_factory=list)
    unindexed_markdown: list[str] = field(default_factory=list)
    owner_issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.broken_links or self.unindexed_markdown or self.owner_issues)


def _markdown_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def _link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if " \"" in target:
        target = target.split(" \"", 1)[0]
    return unquote(target.split("#", 1)[0].split("?", 1)[0]).strip()


def _local_link_paths(path: Path) -> list[tuple[str, Path]]:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Cannot read documentation file: {path.name}") from exc
    links: list[tuple[str, Path]] = []
    for raw_target in MARKDOWN_LINK.findall(content):
        target = _link_target(raw_target)
        if not target or target.startswith(("#", "/")):
            continue
        if target.lower().startswith(EXTERNAL_PREFIXES):
            continue
        links.append((target, (path.parent / target).resolve()))
    return links


def _indexed_markdown(index_path: Path) -> set[Path]:
    return {
        target
        for _, target in _local_link_paths(index_path)
        if target.suffix.lower() == ".md"
    }


def _scan_links(paths: list[Path], report: DocumentationReport) -> None:
    for path in paths:
        for target, resolved in _local_link_paths(path):
            report.local_links += 1
            if not resolved.exists():
                report.broken_links.append(f"{path.name}: {target}")


def _check_index(root: Path, index_name: str, report: DocumentationReport) -> None:
    index = root / index_name
    if not index.is_file():
        report.unindexed_markdown.append(f"missing index: {index_name}")
        return
    indexed = _indexed_markdown(index)
    for path in _markdown_files(root):
        if path == index:
            continue
        if path.resolve() not in indexed:
            report.unindexed_markdown.append(path.relative_to(root).as_posix())


def _check_generated_manifest(owner_docs: Path, report: DocumentationReport) -> None:
    generated = owner_docs / "generated"
    manifest = generated / "GENERATED_MANIFEST.md"
    if not manifest.is_file():
        report.owner_issues.append("generated manifest is missing")
        return
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        report.owner_issues.append("generated manifest is unreadable")
        return
    rows = [match.groups() for line in lines if (match := MANIFEST_ROW.fullmatch(line))]
    if not rows:
        report.owner_issues.append("generated manifest has no fingerprints")
        return
    for name, expected_hash in rows:
        path = generated / name
        if not path.is_file():
            report.owner_issues.append(f"generated file is missing: {name}")
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            report.owner_issues.append(f"generated fingerprint mismatch: {name}")


def _check_owner_labels(owner_docs: Path, report: DocumentationReport) -> None:
    readme = owner_docs / "README.md"
    if not readme.is_file():
        report.owner_issues.append("owner README is missing")
        return
    content = readme.read_text(encoding="utf-8")
    required_labels = (
        "最新已發布版本",
        "目前工作候選",
        "Latest published release",
        "Active working candidate",
    )
    for label in required_labels:
        if label not in content:
            report.owner_issues.append(f"owner snapshot label is missing: {label}")


def validate(repo_docs: Path, owner_docs: Path | None = None) -> DocumentationReport:
    if not repo_docs.is_dir():
        raise RuntimeError(f"Documentation directory does not exist: {repo_docs}")
    report = DocumentationReport()
    repo_paths = _markdown_files(repo_docs)
    report.markdown_files += len(repo_paths)
    _scan_links(repo_paths, report)
    _check_index(repo_docs, "README.md", report)

    if repo_docs.resolve() == (ROOT / "docs").resolve():
        root_docs = [
            path
            for name in ("README.md", "README_EN.md", "SECURITY.md", "CONTRIBUTING.md")
            if (path := ROOT / name).is_file()
        ]
        report.markdown_files += len(root_docs)
        _scan_links(root_docs, report)

    if owner_docs is not None:
        if not owner_docs.is_dir():
            raise RuntimeError(f"Owner documentation directory does not exist: {owner_docs}")
        owner_paths = _markdown_files(owner_docs)
        report.markdown_files += len(owner_paths)
        _scan_links(owner_paths, report)
        _check_index(owner_docs, "DOCUMENT_INDEX.md", report)
        _check_generated_manifest(owner_docs, report)
        _check_owner_labels(owner_docs, report)

    report.broken_links.sort()
    report.unindexed_markdown.sort()
    report.owner_issues.sort()
    return report


def _resolve_path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate EchoBot documentation links, indexes, and owner evidence metadata.",
    )
    parser.add_argument("--repo-docs", type=Path, default=Path("docs"))
    parser.add_argument("--owner-docs", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compatibility flag: validation is always read-only and exits non-zero on errors.",
    )
    arguments = parser.parse_args()
    try:
        report = validate(
            _resolve_path(arguments.repo_docs).resolve(),
            _resolve_path(arguments.owner_docs).resolve()
            if arguments.owner_docs is not None
            else None,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(
        "documentation_check "
        f"markdown_files={report.markdown_files} "
        f"local_links={report.local_links} "
        f"broken_links={len(report.broken_links)} "
        f"unindexed_markdown={len(report.unindexed_markdown)} "
        f"owner_issues={len(report.owner_issues)}"
    )
    for issue in report.broken_links:
        print(f"broken link: {issue}", file=sys.stderr)
    for issue in report.unindexed_markdown:
        print(f"unindexed markdown: {issue}", file=sys.stderr)
    for issue in report.owner_issues:
        print(f"owner issue: {issue}", file=sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
