from __future__ import annotations

from dataclasses import dataclass

from .parsing import split_command_parts


@dataclass(slots=True)
class SmokeCommand:
    text: str


def parse_smoke_command(text: str) -> SmokeCommand | None:
    command_token, remainder = split_command_parts(text)
    if command_token not in {"/ping", "/smoke"}:
        return None
    cleaned = remainder.strip()
    if not cleaned:
        cleaned = "pong"
    return SmokeCommand(text=cleaned[:200])


def execute_smoke_command(command: SmokeCommand) -> str:
    return command.text


def format_smoke_help() -> list[str]:
    return [
        "Gateway smoke commands:",
        "/ping [text] - Reply with text exactly for platform E2E checks",
        "/smoke [text] - Alias for /ping",
    ]
