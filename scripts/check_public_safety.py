from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_TRACKED_PATHS = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.private",
    ".echobot/channels.json",
}

FORBIDDEN_TRACKED_PREFIXES = (
    ".echobot/",
    ".uv-cache/",
)

SCANNED_SECRET_PATTERNS = {
    "telegram_bot_token": re.compile(r"\b\d{8,12}:AA[A-Za-z0-9_-]{30,}\b"),
    "openai_api_key": re.compile(r"\bsk-[A-Za-z0-9A-Za-z_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "discord_bot_token": re.compile(
        r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b",
    ),
    "discord_mfa_token": re.compile(r"\bmfa\.[A-Za-z0-9_-]{20,}\b"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
}

SCAN_EXCLUDED_PREFIXES = (
    ".git/",
    ".venv/",
    ".uv-cache/",
    "venv/",
    "node_modules/",
    "echobot/app/web/vendor/",
)

SCAN_EXCLUDED_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".mp3",
    ".wav",
    ".wasm",
)


def main() -> int:
    candidate_files = _git_candidate_files()
    findings: list[str] = []
    findings.extend(_tracked_path_findings(candidate_files))
    findings.extend(_secret_pattern_findings(candidate_files))

    if findings:
        print("Public safety check failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1

    print("Public safety check passed.")
    return 0


def _git_candidate_files() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        text=True,
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def _tracked_path_findings(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        if path in FORBIDDEN_TRACKED_PATHS:
            findings.append(f"forbidden tracked runtime file: {path}")
            continue
        if any(path.startswith(prefix) for prefix in FORBIDDEN_TRACKED_PREFIXES):
            findings.append(f"forbidden tracked runtime directory: {path}")
            continue
        if _looks_like_env_file(path) and not path.endswith(".example"):
            findings.append(f"non-example env file is tracked: {path}")
    return findings


def _secret_pattern_findings(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        if _should_skip_secret_scan(path):
            continue
        full_path = ROOT / path
        try:
            text = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern_name, pattern in SCANNED_SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{pattern_name} pattern found in {path}")
    return findings


def _should_skip_secret_scan(path: str) -> bool:
    return (
        any(path.startswith(prefix) for prefix in SCAN_EXCLUDED_PREFIXES)
        or path.endswith(SCAN_EXCLUDED_SUFFIXES)
    )


def _looks_like_env_file(path: str) -> bool:
    name = Path(path).name
    return name == ".env" or name.startswith(".env.")


if __name__ == "__main__":
    raise SystemExit(main())
