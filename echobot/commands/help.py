from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .parsing import split_command_parts
from .role import format_role_help
from .route_mode import format_route_mode_help
from .route_sessions import format_route_session_help
from .runtime import format_runtime_help
from .saved_sessions import format_saved_session_help_lines
from .smoke import format_smoke_help


@dataclass(slots=True)
class HelpCommand:
    action: str = "help"


def parse_help_command(text: str) -> HelpCommand | None:
    command_token, _remainder = split_command_parts(text)
    if command_token != "/help":
        return None
    return HelpCommand()


def format_cli_help() -> str:
    return _join_help_sections(
        [
            [
                "Available commands:",
                "/help - Show this help",
                "exit or quit - Stop the chat",
                "clear or /clear - Clear the conversation history",
            ],
            format_saved_session_help_lines(),
            format_role_help().splitlines(),
            format_route_mode_help().splitlines(),
            format_runtime_help().splitlines(),
        ]
    )


def format_gateway_help() -> str:
    return _join_help_sections(
        [
            [
                "Available commands:",
                "/help - Show this help",
            ],
            format_smoke_help(),
            format_route_session_help().splitlines(),
            format_role_help().splitlines(),
            format_route_mode_help().splitlines(),
            format_runtime_help().splitlines(),
        ]
    )


def _join_help_sections(sections: Iterable[Sequence[str]]) -> str:
    blocks = ["\n".join(section) for section in sections if section]
    return "\n\n".join(blocks)
