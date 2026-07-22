from __future__ import annotations

import argparse
from pathlib import Path

from ..runtime.bootstrap import RuntimeOptions


SESSION_STORE_BACKENDS = ("jsonl", "sqlite")


def add_runtime_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_session: bool = False,
) -> None:
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to the environment file. Default: .env",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Workspace root. Default: current directory",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Optional model temperature.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Optional max output tokens.",
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Disable the built-in basic tools.",
    )
    parser.add_argument(
        "--no-skills",
        action="store_true",
        help="Disable discovered project skills.",
    )
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Disable ReMeLight-based memory support.",
    )
    parser.add_argument(
        "--no-heartbeat",
        action="store_true",
        help="Disable heartbeat checks for this run.",
    )
    parser.add_argument(
        "--session-store-backend",
        choices=SESSION_STORE_BACKENDS,
        default="jsonl",
        help="Session persistence backend. Default: jsonl",
    )
    parser.add_argument(
        "--agent-session-store-backend",
        choices=SESSION_STORE_BACKENDS,
        default=None,
        help=(
            "Optional backend for agent session persistence. "
            "Defaults to --session-store-backend."
        ),
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=None,
        help="Override heartbeat interval in seconds for this run.",
    )
    if include_session:
        parser.add_argument(
            "--session",
            default=None,
            help="Load or create the given session name.",
        )
        parser.add_argument(
            "--new-session",
            default=None,
            help="Create a new empty session with the given name.",
        )


def runtime_options_from_args(args: argparse.Namespace) -> RuntimeOptions:
    workspace = build_workspace_path(getattr(args, "workspace", None))
    env_file_path = resolve_runtime_path(
        getattr(args, "env_file", ".env"),
        workspace,
    )
    return RuntimeOptions(
        env_file=str(env_file_path),
        workspace=workspace,
        temperature=getattr(args, "temperature", None),
        max_tokens=getattr(args, "max_tokens", None),
        no_tools=bool(getattr(args, "no_tools", False)),
        no_skills=bool(getattr(args, "no_skills", False)),
        no_memory=bool(getattr(args, "no_memory", False)),
        no_heartbeat=bool(getattr(args, "no_heartbeat", False)),
        heartbeat_interval=getattr(args, "heartbeat_interval", None),
        session=getattr(args, "session", None),
        new_session=getattr(args, "new_session", None),
        session_store_backend=getattr(args, "session_store_backend", "jsonl"),
        agent_session_store_backend=getattr(
            args,
            "agent_session_store_backend",
            None,
        ),
    )


def build_workspace_path(raw_workspace: str | None) -> Path | None:
    if raw_workspace is None:
        return None
    return Path(raw_workspace).expanduser().resolve()


def resolve_runtime_path(path: str | Path, workspace: Path | None) -> Path:
    resolved_path = Path(path).expanduser()
    if resolved_path.is_absolute() or workspace is None:
        return resolved_path
    return workspace / resolved_path
