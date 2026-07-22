from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_repo_file(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_local_tunnel_docs_separate_compose_and_container_environment() -> None:
    guide = read_repo_file("docs/deployment/local-tunnel.md")

    assert "cp .env.local-tunnel.example docker.env.local" in guide
    assert "docker compose --env-file docker.env.local config" in guide
    assert "docker.env.local" in guide
    assert "LLM_API_KEY" in guide
    assert "docker compose cp echobot:/app/.echobot" in guide
    assert "stale connections" in guide
    assert "失效連線" in guide


def test_production_docker_docs_do_not_direct_users_to_bypass_access() -> None:
    guide = read_repo_file("docs/deployment/docker.md")

    assert "docker login ghcr.io" in guide
    assert "ECHOBOT_ADMIN_ALLOWLIST" in guide
    assert "http://127.0.0.1:8080/healthz" in guide
    assert "https://echobot.example.com/console" in guide
    assert "Do not open protected pages through `http://127.0.0.1:8080`" in guide
    assert "不要透過 `http://127.0.0.1:8080` 開啟受保護頁面" in guide


def test_readme_has_current_display_modes_and_first_success_path() -> None:
    chinese = read_repo_file("README.md")
    english = read_repo_file("README_EN.md")

    assert "自動、手機、平板、桌面 / 密集" in chinese
    assert "自動、手機、直向、橫向" not in chinese
    assert "Auto, Mobile, Tablet, Desktop / Dense" in english
    assert "Auto, Mobile, Portrait, Landscape" not in english
    for route in (
        "/admin/models",
        "/admin/characters",
        "/admin/sessions",
        "/console",
        "/stage?session_name=demo",
    ):
        assert route in chinese
        assert route in english
    assert "ECHOBOT_ASR_SHERPA_AUTO_DOWNLOAD=false" in chinese
    assert "ECHOBOT_VAD_SILERO_AUTO_DOWNLOAD=false" in chinese
    assert "ECHOBOT_ASR_SHERPA_AUTO_DOWNLOAD=false" in english
    assert "ECHOBOT_VAD_SILERO_AUTO_DOWNLOAD=false" in english


def test_security_baseline_and_contributor_prerequisites_are_complete() -> None:
    security = read_repo_file("SECURITY.md")
    contributing = read_repo_file("CONTRIBUTING.md")

    for setting in (
        "ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true",
        "ECHOBOT_TRUSTED_USER_REQUIRED=true",
        "ECHOBOT_TRUSTED_USER_ASSERTION_REQUIRED=true",
        "ECHOBOT_ADMIN_ALLOWLIST=admin@example.com",
        "ECHOBOT_ADMIN_REQUIRED=true",
        "ECHOBOT_DEPLOYMENT_PROFILE=tunnel",
    ):
        assert setting in security
    assert "GitHub Security Advisory" in security
    assert "requirements-dev.txt" in contributing
    assert "playwright install chromium" in contributing


def test_session_configuration_api_and_current_ui_behaviors_are_documented() -> None:
    site_structure = read_repo_file("docs/implementation/echobot-web-site-structure.md")
    readme = read_repo_file("README.md")

    assert "PUT /api/sessions/{session_name}/configuration" in site_structure
    for behavior in (
        "Stage 全螢幕",
        "控制列自動隱藏",
        "模型與語音搜尋",
        "Applied to Stage",
    ):
        assert behavior in readme
