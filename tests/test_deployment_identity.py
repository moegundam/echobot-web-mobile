from __future__ import annotations

import asyncio
from pathlib import Path
from echobot.app.routers import deployment as deployment_router
from echobot.app.services import deployment_status


class _FakeRuntime:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    async def health_snapshot(self):
        return {
            "status": "ok",
            "channels": {},
            "current_session": "",
        }


def test_deployment_status_includes_source_identity_when_route_invoked(tmp_path: Path) -> None:
    workspace = tmp_path
    result = asyncio.run(
        deployment_router.get_deployment_status(
            _FakeRuntime(workspace),
            _admin_user="admin",
        ),
    )

    assert "source_identity" in result
    identity = result["source_identity"]
    assert identity["version"] == "unknown"
    assert identity["branch"] == "unknown"
    assert identity["dirty"] == "unknown"
    assert identity["checkout_status"] == "unknown"
    assert identity["worktree_status"] == "unknown"


def test_source_identity_snapshot_uses_git_output(monkeypatch, tmp_path: Path) -> None:
    outputs = {
        ("rev-parse", "--short", "HEAD"): "abc1234",
        ("rev-parse", "--abbrev-ref", "HEAD"): "main",
        ("status", "--porcelain", "--untracked-files=normal"): "?? new-file.py",
    }

    def fake_git_output(command: list[str], _workspace: Path) -> str | None:
        return outputs.get(tuple(command))

    monkeypatch.setattr(deployment_status, "_git_output", fake_git_output)

    identity = deployment_status._source_identity_snapshot(tmp_path)

    assert identity == {
        "version": "abc1234",
        "branch": "main",
        "dirty": True,
        "checkout_status": "attached",
        "worktree_status": "dirty",
    }


def test_source_identity_snapshot_uses_unknown_for_failing_git(tmp_path: Path) -> None:
    identity = deployment_status._source_identity_snapshot(tmp_path)

    assert identity == {
        "version": "unknown",
        "branch": "unknown",
        "dirty": "unknown",
        "checkout_status": "unknown",
        "worktree_status": "unknown",
    }


def test_deployment_commands_do_not_hardcode_a_developer_port(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ECHOBOT_PUBLIC_BASE_URL", raising=False)
    system = {
        "cloudflare": {"named_tunnel_ready": False},
        "github_actions": {"node24_ready": True},
        "source_identity": {},
        "openwebui": {},
    }
    payload = deployment_status._deployment_status_payload(
        health={"status": "ok"},
        workspace=tmp_path,
        system=system,
    )

    commands = "\n".join(payload["commands"])
    assert "127.0.0.1:8001" not in commands
    assert "<ECHOBOT-BASE-URL>" in commands

    monkeypatch.setenv("ECHOBOT_PUBLIC_BASE_URL", "https://echo.example.test/")
    configured = deployment_status._deployment_status_payload(
        health={"status": "ok"},
        workspace=tmp_path,
        system=system,
    )
    configured_commands = "\n".join(configured["commands"])
    assert "--base-url https://echo.example.test" in configured_commands
