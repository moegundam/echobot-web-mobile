from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_uses_hardened_runtime_defaults() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM cgr.dev/chainguard/wolfi-base@sha256:" in dockerfile
    assert " AS python-base" in dockerfile
    assert " AS builder" in dockerfile
    assert " AS runtime" in dockerfile
    assert ":latest" not in dockerfile
    assert "python-3.12" in dockerfile
    assert "USER 65532:65532" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "urlopen('http://127.0.0.1:8000/healthz', timeout=5)" in dockerfile
    assert "ECHOBOT_SHELL_SAFETY_MODE=workspace-write" in dockerfile
    assert "LLM_API_KEY=" not in dockerfile
    assert "TELEGRAM_BOT_TOKEN=" not in dockerfile
    assert "DISCORD_BOT_TOKEN=" not in dockerfile
    assert "apk update" not in dockerfile


def test_compose_places_the_app_behind_a_loopback_ingress() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = compose["services"]["echobot"]
    ingress = compose["services"]["ingress"]

    assert service["image"] == "echobot-web-mobile:local"
    assert "ports" not in service
    assert service["expose"] == ["8000"]
    assert "echobot_data:/app/.echobot" in service["volumes"]
    assert "LLM_API_KEY" not in service["environment"]
    assert "ECHOBOT_DEPLOYMENT_PROFILE" in service["environment"]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert "/tmp" in service["tmpfs"]
    assert "urlopen('http://127.0.0.1:8000/healthz', timeout=5)" in service[
        "healthcheck"
    ]["test"][-1]
    assert ingress["image"] == (
        "cgr.dev/chainguard/nginx@"
        "sha256:28bbae890f8266882e75a83ab6a1472d276d2d014a8eeb63d1d2e6d6093b5ed4"
    )
    assert ingress["ports"] == ["127.0.0.1:${ECHOBOT_HOST_PORT:-8080}:8080"]
    assert ingress["user"] == "65532:65532"
    assert ingress["depends_on"]["echobot"]["condition"] == "service_healthy"
    assert "./deploy/nginx/echobot-container.conf:/etc/nginx/nginx.conf:ro" in ingress[
        "volumes"
    ]
    assert ingress["read_only"] is True
    assert ingress["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in ingress["security_opt"]
    assert ingress["healthcheck"]["test"] == [
        "CMD",
        "/usr/bin/wget",
        "--quiet",
        "--tries=1",
        "--timeout=5",
        "--output-document=/dev/null",
        "http://127.0.0.1:8080/healthz",
    ]
    assert compose["volumes"]["echobot_data"] is None


def test_production_compose_requires_an_immutable_image_reference() -> None:
    source = (ROOT / "compose.production.yaml").read_text(encoding="utf-8")
    compose = yaml.safe_load(source)
    service = compose["services"]["echobot"]

    assert service["image"].startswith(
        "ghcr.io/moegundam/echobot-web-mobile@sha256:${ECHOBOT_IMAGE_SHA256:?",
    )
    assert "ECHOBOT_IMAGE_REF" not in source
    assert ":latest" not in service["image"]
    assert ":upgrade" not in service["image"]
    assert "build" not in service
    assert "ports" not in service


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


def test_tunnel_env_template_uses_fail_closed_security_and_bounded_uploads() -> None:
    template = (ROOT / ".env.local-tunnel.example").read_text(encoding="utf-8")

    assert "ECHOBOT_DEPLOYMENT_PROFILE=tunnel" in template
    assert "ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true" in template
    assert "ECHOBOT_TRUSTED_USER_REQUIRED=true" in template
    assert "ECHOBOT_ADMIN_REQUIRED=true" in template
    assert "ECHOBOT_FILE_MAX_INPUT_BYTES=26214400" in template


def test_nginx_ingress_limits_requests_before_the_application_parser() -> None:
    config = (ROOT / "deploy" / "nginx" / "echobot.conf").read_text(
        encoding="utf-8",
    )

    assert "listen 127.0.0.1:8080" in config
    assert "server 127.0.0.1:8000" in config
    container_config = (ROOT / "deploy" / "nginx" / "echobot-container.conf").read_text(
        encoding="utf-8",
    )

    assert "client_max_body_size 2m" in config
    assert "location = /api/attachments/images" in config
    assert "client_max_body_size 42m" in config
    assert "location = /api/attachments/files" in config
    assert "client_max_body_size 27m" in config
    assert "location = /api/web/stage/backgrounds" in config
    assert "client_max_body_size 11m" in config
    assert "location = /api/web/live2d" in config
    assert "client_max_body_size 210m" in config
    assert "map $http_cf_access_authenticated_user_email $echobot_identity_key" in config
    assert "zone=echobot_api_identity" in config
    assert "zone=echobot_api_global" in config
    assert "limit_conn_zone" in config
    assert "limit_req_status 429" in config
    assert "limit_conn_status 429" in config
    assert "limit_req zone=echobot_api_identity" in config
    assert "limit_req zone=echobot_api_global" in config
    assert "limit_conn echobot_streams" in config
    assert "limit_conn echobot_global_streams" in config
    assert "proxy_buffering off" in config
    assert "proxy_request_buffering on" in config
    assert "fastcgi_temp_path /tmp/" in config
    assert "scgi_temp_path /tmp/" in config
    assert "uwsgi_temp_path /tmp/" in config
    assert "proxy_set_header Upgrade $http_upgrade" in config
    assert "proxy_set_header Connection $connection_upgrade" in config
    assert "proxy_set_header X-Forwarded-Proto https" in config
    assert "resolver 127.0.0.11 valid=5s ipv6=off" in container_config
    assert "resolver_timeout 2s" in container_config
    assert "zone echobot_app 64k" in container_config
    assert "server echobot:8000 resolve" in container_config
    assert "listen 8080" in container_config
    assert "server 127.0.0.1:8000" not in container_config


def test_ci_validates_the_production_ingress_config_in_the_pinned_container() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
    )
    production = yaml.safe_load(
        (ROOT / "compose.production.yaml").read_text(encoding="utf-8"),
    )
    ingress = production["services"]["ingress"]

    assert workflow["env"]["ECHOBOT_INGRESS_IMAGE"] == ingress["image"]

    validation_step = next(
        step
        for step in workflow["jobs"]["test"]["steps"]
        if step.get("name") == "Validate production ingress container config"
    )
    run = validation_step["run"]

    assert '"${ECHOBOT_INGRESS_IMAGE}"' in run
    assert (
        '"${GITHUB_WORKSPACE}/deploy/nginx/echobot-container.conf:'
        '/etc/nginx/nginx.conf:ro"'
    ) in run
    assert "--entrypoint /usr/sbin/nginx" in run
    assert "--add-host echobot:127.0.0.1" in run
    assert "--user 65532:65532" in run
    assert "--read-only" in run
    assert "--cap-drop ALL" in run
    assert "--security-opt no-new-privileges:true" in run
    assert "--tmpfs /var/cache/nginx" in run
    assert "--tmpfs /var/run" in run
    assert "--tmpfs /tmp" in run
    assert "-e stderr" in run
    assert "-t" in run
    assert "-c /etc/nginx/nginx.conf" in run

    replacement_step = next(
        step
        for step in workflow["jobs"]["test"]["steps"]
        if step.get("name") == "Compose app replacement smoke"
    )
    assert "scripts/compose_replacement_smoke.py" in replacement_step["run"]


def test_compose_replacement_smoke_requires_new_app_ip_without_ingress_restart() -> None:
    source = (ROOT / "scripts" / "compose_replacement_smoke.py").read_text(
        encoding="utf-8",
    )

    assert "old_app_ip" in source
    assert "new_app_ip" in source
    assert "old_app_ip == new_app_ip" in source
    assert "original_ingress_id" in source
    assert "current_ingress_id" in source
    assert "original_ingress_id != current_ingress_id" in source
    assert "/healthz" in source


def test_ingress_smoke_uses_an_observable_mock_upstream() -> None:
    source = (ROOT / "scripts" / "ingress_smoke.py").read_text(encoding="utf-8")

    assert "ThreadingHTTPServer" in source
    assert "manage_mock_upstream" in source
    assert "upstream_hits" in source
    assert "oversized_chunked" in source
    assert "allowed_multipart" in source
    assert "status <= 0" in source


def test_cloudflared_template_routes_through_bounded_ingress() -> None:
    config = (
        ROOT / "docs" / "deployment" / "cloudflared-local-tunnel.example.yml"
    ).read_text(encoding="utf-8")

    assert "service: http://127.0.0.1:8080" in config
    assert "service: http://127.0.0.1:8000" not in config
