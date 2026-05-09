from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..services.openwebui_bridge import openwebui_bridge_status
from ..state import require_admin_user


router = APIRouter(tags=["deployment"])

_ORIGIN_CERT_CANDIDATES = (
    "~/.cloudflared/cert.pem",
    "~/.cloudflare-warp/cert.pem",
    "~/cloudflare-warp/cert.pem",
    "/etc/cloudflared/cert.pem",
    "/usr/local/etc/cloudflared/cert.pem",
)


@router.get("/deployment/status")
async def get_deployment_status(
    request: Request,
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, Any]:
    runtime = request.app.state.runtime
    health = await runtime.health_snapshot()
    workspace = runtime.workspace
    cloudflared = _cloudflared_status()
    ci = _github_actions_status(workspace)
    return {
        "local": {
            "health": health.get("status", "unknown"),
            "workspace_name": workspace.name,
            "current_session": health.get("current_session", ""),
            "channels": health.get("channels", {}),
        },
        "cloudflare": cloudflared,
        "github_actions": ci,
        "openwebui": openwebui_bridge_status(),
        "simple_deploy": {
            "recommended_mode": "guided",
            "enabled": False,
            "reason": (
                "Use read-only checks and generated commands first. Cloudflare login, "
                "origin certificates, DNS routes, and Access policies are external "
                "account operations."
            ),
            "future_inputs": [
                "hostname",
                "access_emails",
                "local_port",
                "tunnel_name",
                "target_user_id",
            ],
        },
        "commands": [
            "python scripts/echobot_entrypoint.py doctor",
            "python scripts/echobot_entrypoint.py status",
            "python scripts/openwebui_bridge_smoke.py --base-url http://127.0.0.1:8001 --session-name demo",
            "cloudflared tunnel login",
            "cloudflared tunnel ingress validate <config.yml>",
        ],
        "readiness": _readiness_summary(cloudflared, ci),
    }


def _cloudflared_status() -> dict[str, Any]:
    binary = shutil.which("cloudflared")
    version = ""
    if binary:
        version = _command_output([binary, "--version"])
    origin_cert_env = os.environ.get("TUNNEL_ORIGIN_CERT", "").strip()
    cert_candidates = [origin_cert_env] if origin_cert_env else []
    cert_candidates.extend(_ORIGIN_CERT_CANDIDATES)
    cert_path = _first_existing_path(cert_candidates)
    return {
        "cli_installed": bool(binary),
        "binary": binary or "",
        "version": version,
        "origin_cert_present": bool(cert_path),
        "origin_cert_path": _display_path(cert_path) if cert_path else "",
        "named_tunnel_ready": bool(binary and cert_path),
        "status": "ready" if binary and cert_path else "warning",
        "next_steps": _cloudflare_next_steps(bool(binary), bool(cert_path)),
        "next_step_keys": _cloudflare_next_step_keys(bool(binary), bool(cert_path)),
    }


def _github_actions_status(workspace: Path) -> dict[str, Any]:
    workflow_path = workspace / ".github" / "workflows" / "ci.yml"
    if not workflow_path.exists():
        return {
            "workflow_exists": False,
            "checkout_action": "",
            "setup_python_action": "",
            "node24_ready": False,
            "status": "warning",
        }
    text = workflow_path.read_text(encoding="utf-8")
    checkout_action = _first_action_version(text, "actions/checkout")
    setup_python_action = _first_action_version(text, "actions/setup-python")
    node24_ready = _major_version(checkout_action) >= 6 and _major_version(setup_python_action) >= 6
    return {
        "workflow_exists": True,
        "checkout_action": checkout_action,
        "setup_python_action": setup_python_action,
        "node24_ready": node24_ready,
        "status": "ready" if node24_ready else "warning",
    }


def _readiness_summary(
    cloudflared: dict[str, Any],
    ci: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "name": "Local EchoBot",
            "name_key": "deployment.readiness.localEchoBot",
            "status": "ready",
            "detail": "Local API health is reachable through the running app.",
            "detail_key": "deployment.readiness.localReady",
        },
        {
            "name": "GitHub Actions",
            "name_key": "deployment.readiness.githubActions",
            "status": "ready" if ci.get("node24_ready") else "warning",
            "detail": (
                "CI actions are on Node 24-ready major versions."
                if ci.get("node24_ready")
                else "Update checkout/setup-python actions before relying on CI warnings."
            ),
            "detail_key": (
                "deployment.readiness.ciReady"
                if ci.get("node24_ready")
                else "deployment.readiness.ciWarning"
            ),
        },
        {
            "name": "Cloudflare Tunnel",
            "name_key": "deployment.readiness.cloudflareTunnel",
            "status": "ready" if cloudflared.get("named_tunnel_ready") else "warning",
            "detail": (
                "cloudflared CLI and origin cert are present."
                if cloudflared.get("named_tunnel_ready")
                else "Run Cloudflare login and create/configure a named tunnel before HTTPS mobile acceptance."
            ),
            "detail_key": (
                "deployment.readiness.cloudflareReady"
                if cloudflared.get("named_tunnel_ready")
                else "deployment.readiness.cloudflareWarning"
            ),
        },
    ]


def _cloudflare_next_steps(cli_installed: bool, cert_present: bool) -> list[str]:
    steps: list[str] = []
    if not cli_installed:
        steps.append("Install cloudflared.")
    if cli_installed and not cert_present:
        steps.append("Run cloudflared tunnel login to create an origin certificate.")
    if cli_installed and cert_present:
        steps.append("Create a named tunnel, route DNS, and configure Access policy.")
    steps.append("Validate ingress config before starting real-device HTTPS tests.")
    return steps


def _cloudflare_next_step_keys(cli_installed: bool, cert_present: bool) -> list[str]:
    step_keys: list[str] = []
    if not cli_installed:
        step_keys.append("deployment.nextStep.installCloudflared")
    if cli_installed and not cert_present:
        step_keys.append("deployment.nextStep.loginCloudflare")
    if cli_installed and cert_present:
        step_keys.append("deployment.nextStep.createTunnel")
    step_keys.append("deployment.nextStep.validateIngress")
    return step_keys


def _command_output(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except OSError:
        return ""
    except subprocess.TimeoutExpired:
        return "timeout"
    return (completed.stdout or completed.stderr).strip()


def _first_existing_path(candidates: list[str] | tuple[str, ...]) -> Path | None:
    for item in candidates:
        if not item:
            continue
        path = Path(item).expanduser()
        if path.exists():
            return path
    return None


def _display_path(path: Path) -> str:
    home = Path.home()
    try:
        return "~/" + str(path.expanduser().relative_to(home))
    except ValueError:
        return str(path)


def _first_action_version(text: str, action_name: str) -> str:
    match = re.search(rf"uses:\s*{re.escape(action_name)}@([^\s#]+)", text)
    if match is None:
        return ""
    return f"{action_name}@{match.group(1)}"


def _major_version(action_ref: str) -> int:
    match = re.search(r"@v(\d+)", action_ref)
    if match is None:
        return 0
    return int(match.group(1))
