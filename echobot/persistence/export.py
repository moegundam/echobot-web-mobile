from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..channels import load_channels_config
from ..runtime.sessions import SessionStore


def build_postgres_seed_export(workspace: str | Path) -> dict[str, Any]:
    workspace_path = Path(workspace)
    storage_root = workspace_path / ".echobot"
    return {
        "format": "echobot-postgres-seed-v1",
        "sessions": _export_sessions(storage_root / "sessions"),
        "model_profiles": _read_json(storage_root / "model_profiles.json"),
        "llm_models": _read_json(storage_root / "llm_models.json"),
        "voice_profiles": _read_json(storage_root / "voice_profiles.json"),
        "live2d_models": _read_json(storage_root / "live2d_models.json"),
        "character_profiles": _read_json(storage_root / "character_profiles.json"),
        "channels": _export_channels(storage_root / "channels.json"),
        "notes": [
            "Secrets are not exported. Recreate API keys, bot tokens, and webhook secrets in the target secret store.",
            "This export is a migration seed for the future PostgreSQL adapter; the current runtime remains file-backed unless configured otherwise.",
        ],
    }


def write_postgres_seed_export(workspace: str | Path, output_path: str | Path) -> None:
    payload = build_postgres_seed_export(workspace)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _export_sessions(session_dir: Path) -> list[dict[str, Any]]:
    store = SessionStore(session_dir)
    sessions: list[dict[str, Any]] = []
    for info in store.list_sessions():
        try:
            session = store.load_session(info.name)
        except ValueError:
            continue
        sessions.append(
            {
                "name": session.name,
                "updated_at": session.updated_at,
                "compressed_summary": session.compressed_summary,
                "metadata": dict(session.metadata),
                "history": [
                    {
                        "role": message.role,
                        "content": message.content,
                        "name": message.name,
                        "tool_call_id": message.tool_call_id,
                    }
                    for message in session.history
                ],
            }
        )
    return sessions


def _export_channels(path: Path) -> dict[str, Any]:
    config = load_channels_config(path, create_default=False).to_dict()
    for channel_config in config.values():
        if not isinstance(channel_config, dict):
            continue
        for key in list(channel_config):
            if _is_secret_key(key):
                configured = bool(str(channel_config.get(key) or "").strip())
                channel_config[key] = ""
                channel_config[f"{key}_configured"] = configured
    return config


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _is_secret_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    return normalized in {
        "api_key",
        "bot_token",
        "client_secret",
        "webhook_secret",
    }
