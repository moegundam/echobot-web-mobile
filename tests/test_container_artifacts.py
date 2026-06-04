from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_uses_hardened_runtime_defaults() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM cgr.dev/chainguard/wolfi-base@sha256:" in dockerfile
    assert " AS builder" in dockerfile
    assert " AS runtime" in dockerfile
    assert ":latest" not in dockerfile
    assert "python-3.12" in dockerfile
    assert "USER 65532:65532" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "ECHOBOT_SHELL_SAFETY_MODE=workspace-write" in dockerfile
    assert "LLM_API_KEY=" not in dockerfile
    assert "TELEGRAM_BOT_TOKEN=" not in dockerfile
    assert "DISCORD_BOT_TOKEN=" not in dockerfile


def test_compose_uses_loopback_volume_and_restricted_runtime() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = compose["services"]["echobot"]

    assert service["image"] == "ghcr.io/moegundam/echobot-web-mobile:upgrade"
    assert service["ports"] == ["127.0.0.1:${ECHOBOT_HOST_PORT:-8000}:8000"]
    assert "echobot_data:/app/.echobot" in service["volumes"]
    assert "LLM_API_KEY" not in service["environment"]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert "/tmp" in service["tmpfs"]
    assert compose["volumes"]["echobot_data"] is None


def test_docker_ignore_excludes_runtime_and_secrets() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    for pattern in (
        ".env",
        ".env.*",
        ".echobot/",
        ".venv/",
        "docker.env.local",
        "tests/",
        "docs/",
    ):
        assert pattern in dockerignore


def test_docker_env_template_is_non_secret() -> None:
    template = (ROOT / "docker.env.example").read_text(encoding="utf-8")

    assert "LLM_API_KEY=" in template
    assert "TELEGRAM_BOT_TOKEN=" in template
    assert "DISCORD_BOT_TOKEN=" in template
    assert "sk-" not in template
    assert ":AA" not in template
