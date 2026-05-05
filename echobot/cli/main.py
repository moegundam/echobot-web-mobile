from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import app, chat, db, gateway


COMMAND_NAMES = {"chat", "gateway", "app", "db"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified CLI for EchoBot.",
    )
    subparsers = parser.add_subparsers(dest="command")

    chat.configure_parser(
        subparsers.add_parser(
            "chat",
            help="Run the interactive chat CLI.",
        ),
    )
    gateway.configure_parser(
        subparsers.add_parser(
            "gateway",
            help="Run the multi-channel gateway.",
        ),
    )
    app.configure_parser(
        subparsers.add_parser(
            "app",
            help="Run the API daemon for the web console.",
        ),
    )
    db.configure_parser(
        subparsers.add_parser(
            "db",
            help="PostgreSQL schema and migration helper commands.",
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    normalized_argv = _normalize_argv(argv)
    args = parser.parse_args(normalized_argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        raise SystemExit(2)

    result = handler(args)
    if isinstance(result, int):
        raise SystemExit(result)


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args:
        return ["chat"]

    first = raw_args[0]
    if first in COMMAND_NAMES or first in {"-h", "--help"}:
        return raw_args
    if first.startswith("-"):
        return ["chat", *raw_args]
    return raw_args
