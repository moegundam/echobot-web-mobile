#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, parse, request


APP_LABEL = "com.moegundam.echobot.app"
OPENWEBUI_TUNNEL_LABEL = "com.moegundam.echobot.openwebui-tunnel"
DEFAULT_LOCAL_HOST = "127.0.0.1"
DEFAULT_LOCAL_PORT = 8001
DEFAULT_REMOTE_HOST = os.environ.get("ECHOBOT_OPENWEBUI_REMOTE_HOST", "")
DEFAULT_REMOTE_BIND = "127.0.0.1"
DEFAULT_REMOTE_PORT = int(os.environ.get("ECHOBOT_OPENWEBUI_REMOTE_PORT", "18001"))
DEFAULT_STATE_DIR = Path(os.environ.get("ECHOBOT_LOCAL_STATE_DIR", "~/.echobot")).expanduser()
DEFAULT_LOG_DIR = DEFAULT_STATE_DIR / "logs"
DEFAULT_TOKEN_FILE = str(DEFAULT_STATE_DIR / "openwebui_bridge_token")
DEFAULT_TARGET_USER_ID = "echobot-smoke@local"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage durable local EchoBot and Open WebUI bridge entrypoints.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(_default_repo_root()),
        help="EchoBot checkout root. Defaults to this script's repository.",
    )
    parser.add_argument("--host", default=DEFAULT_LOCAL_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_LOCAL_PORT)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--channel-config", default=".echobot/channels.json")
    parser.add_argument(
        "--token-file",
        default=os.environ.get("ECHOBOT_OPENWEBUI_BRIDGE_TOKEN_FILE", DEFAULT_TOKEN_FILE),
        help="Runtime-only bridge token file used by launchd and smoke checks.",
    )
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-bind", default=DEFAULT_REMOTE_BIND)
    parser.add_argument("--remote-port", type=int, default=DEFAULT_REMOTE_PORT)
    parser.add_argument("--python", default="")
    parser.add_argument("--ssh", default=shutil.which("ssh") or "/usr/bin/ssh")

    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="Check local prerequisites.")
    doctor_parser.add_argument("--json", action="store_true", help="Reserved for future use.")

    write_parser = subparsers.add_parser(
        "write-launchd",
        help="Write launchd plists for the app and/or Open WebUI reverse tunnel.",
    )
    write_parser.add_argument(
        "--component",
        choices=["app", "openwebui-tunnel", "all"],
        default="all",
    )
    write_parser.add_argument(
        "--start",
        action="store_true",
        help="Bootstrap launchd services after writing plists.",
    )
    write_parser.add_argument(
        "--restart",
        action="store_true",
        help="Boot out an existing launchd service before starting it.",
    )

    subparsers.add_parser("status", help="Show launchd and HTTP health status.")

    start_parser = subparsers.add_parser("start", help="Bootstrap launchd services.")
    start_parser.add_argument(
        "--component",
        choices=["app", "openwebui-tunnel", "all"],
        default="all",
    )
    start_parser.add_argument("--restart", action="store_true")

    stop_parser = subparsers.add_parser("stop", help="Boot out launchd services.")
    stop_parser.add_argument(
        "--component",
        choices=["app", "openwebui-tunnel", "all"],
        default="all",
    )

    smoke_parser = subparsers.add_parser(
        "smoke-openwebui",
        help="Run Open WebUI bridge smoke through the local or remote entrypoint.",
    )
    smoke_parser.add_argument(
        "--target",
        choices=["local", "remote"],
        default="local",
    )
    smoke_parser.add_argument("--session-name", default="openwebui-smoke")
    smoke_parser.add_argument(
        "--target-user-id",
        default=DEFAULT_TARGET_USER_ID,
        help=(
            "Bridge target user namespace for smoke writes. "
            f"Defaults to {DEFAULT_TARGET_USER_ID} because the bridge requires a target user."
        ),
    )
    smoke_parser.add_argument("--chat-prompt", default="")

    args = parser.parse_args()
    config = _config_from_args(args)

    if args.command == "doctor":
        return _doctor(config)
    if args.command == "write-launchd":
        _write_launchd(config, args.component)
        if args.start:
            return _start(config, args.component, restart=args.restart)
        return 0
    if args.command == "status":
        return _status(config)
    if args.command == "start":
        return _start(config, args.component, restart=args.restart)
    if args.command == "stop":
        return _stop(config, args.component)
    if args.command == "smoke-openwebui":
        return _smoke_openwebui(config, args.target, args.session_name, args.target_user_id, args.chat_prompt)
    return 2


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _config_from_args(args: argparse.Namespace) -> dict[str, object]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    python_path = Path(args.python).expanduser() if args.python else repo_root / ".venv" / "bin" / "python"
    return {
        "repo_root": repo_root,
        "host": str(args.host),
        "port": int(args.port),
        "env_file": str(args.env_file),
        "channel_config": str(args.channel_config),
        "token_file": str(args.token_file or ""),
        "remote_host": str(args.remote_host),
        "remote_bind": str(args.remote_bind),
        "remote_port": int(args.remote_port),
        "python": str(python_path),
        "ssh": str(args.ssh),
        "log_dir": DEFAULT_LOG_DIR,
        "launch_agent_dir": Path.home() / "Library" / "LaunchAgents",
    }


def _doctor(config: dict[str, object]) -> int:
    checks: list[tuple[str, str, str]] = []
    repo_root = Path(config["repo_root"])
    python_path = Path(str(config["python"]))
    token_file = Path(str(config["token_file"]))
    channel_config = repo_root / str(config["channel_config"])

    checks.append(("cwd", "ok" if repo_root.exists() else "fail", str(repo_root)))
    checks.append(("python", "ok" if python_path.exists() else "fail", str(python_path)))
    checks.append(("channel_config", "ok" if channel_config.exists() else "warn", str(channel_config)))
    checks.append(("token_file", "ok" if token_file.exists() and token_file.stat().st_size > 0 else "warn", str(token_file)))
    checks.append(("ssh", "ok" if shutil.which(str(config["ssh"])) or Path(str(config["ssh"])).exists() else "fail", str(config["ssh"])))
    checks.append(("cloudflared", "ok" if shutil.which("cloudflared") else "warn", shutil.which("cloudflared") or "not found"))

    local_url = _local_base_url(config)
    checks.append(("local_health", "ok" if _http_ok(f"{local_url}/api/health") else "warn", local_url))
    remote_url = _remote_base_url(config)
    remote_state = "ok" if _remote_http_ok(config, f"{remote_url}/api/health") else "warn"
    checks.append(("remote_openwebui_reverse_health", remote_state, remote_url))

    if shutil.which("cloudflared"):
        cf = _run(["cloudflared", "tunnel", "list"], check=False)
        cf_state = "ok" if cf.returncode == 0 else "warn"
        cf_detail = "authenticated" if cf.returncode == 0 else _first_line(cf.stderr or cf.stdout)
        checks.append(("cloudflared_auth", cf_state, cf_detail))

    for name, state, detail in checks:
        print(f"{name}: {state} - {detail}")
    return 1 if any(state == "fail" for _, state, _ in checks) else 0


def _write_launchd(config: dict[str, object], component: str) -> None:
    agent_dir = Path(config["launch_agent_dir"])
    log_dir = Path(config["log_dir"])
    agent_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    for label, plist in _selected_plists(config, component):
        path = agent_dir / f"{label}.plist"
        with path.open("wb") as handle:
            plistlib.dump(plist, handle, sort_keys=False)
        print(f"wrote {path}")


def _selected_plists(config: dict[str, object], component: str) -> list[tuple[str, dict[str, object]]]:
    selected: list[tuple[str, dict[str, object]]] = []
    if component in {"app", "all"}:
        selected.append((APP_LABEL, _build_app_plist(config)))
    if component in {"openwebui-tunnel", "all"}:
        if not str(config.get("remote_host") or "").strip():
            if component == "openwebui-tunnel":
                raise ValueError("--remote-host or ECHOBOT_OPENWEBUI_REMOTE_HOST is required for the Open WebUI tunnel")
        else:
            selected.append((OPENWEBUI_TUNNEL_LABEL, _build_openwebui_tunnel_plist(config)))
    return selected


def _build_app_plist(config: dict[str, object]) -> dict[str, object]:
    repo_root = Path(config["repo_root"])
    log_dir = Path(config.get("log_dir") or DEFAULT_LOG_DIR)
    python_path = str(config["python"])
    command = " ".join(
        [
            "cd",
            shlex.quote(str(repo_root)),
            "&&",
            "exec",
            shlex.quote(python_path),
            "-m echobot app",
            "--host",
            shlex.quote(str(config["host"])),
            "--port",
            shlex.quote(str(config["port"])),
            "--workspace",
            shlex.quote(str(repo_root)),
            "--env-file",
            shlex.quote(str(config["env_file"])),
            "--channel-config",
            shlex.quote(str(config["channel_config"])),
        ],
    )
    return {
        "Label": APP_LABEL,
        "ProgramArguments": ["/bin/zsh", "-lc", command],
        "WorkingDirectory": str(repo_root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_dir / "echobot-app.launchd.out.log"),
        "StandardErrorPath": str(log_dir / "echobot-app.launchd.err.log"),
        "EnvironmentVariables": _launchd_env(config),
    }


def _build_openwebui_tunnel_plist(config: dict[str, object]) -> dict[str, object]:
    log_dir = Path(config.get("log_dir") or DEFAULT_LOG_DIR)
    remote_spec = (
        f"{config['remote_bind']}:{config['remote_port']}:"
        f"{config['host']}:{config['port']}"
    )
    return {
        "Label": OPENWEBUI_TUNNEL_LABEL,
        "ProgramArguments": [
            str(config["ssh"]),
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-R",
            remote_spec,
            str(config["remote_host"]),
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_dir / "echobot-openwebui-tunnel.out.log"),
        "StandardErrorPath": str(log_dir / "echobot-openwebui-tunnel.err.log"),
    }


def _launchd_env(config: dict[str, object]) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"),
        "PYTHONUNBUFFERED": "1",
    }
    token_file = str(config.get("token_file") or "")
    if token_file:
        env["ECHOBOT_OPENWEBUI_BRIDGE_TOKEN_FILE"] = token_file
    return env


def _start(config: dict[str, object], component: str, *, restart: bool) -> int:
    failures = 0
    for label, _ in _selected_plists(config, component):
        path = Path(config["launch_agent_dir"]) / f"{label}.plist"
        if restart:
            _launchctl(["bootout", _user_domain(), str(path)], check=False)
        result = _launchctl(["bootstrap", _user_domain(), str(path)], check=False)
        if result.returncode not in (0, 5):
            failures += 1
            print(f"failed to start {label}: {_first_line(result.stderr or result.stdout)}", file=sys.stderr)
            continue
        _launchctl(["kickstart", "-k", f"{_user_domain()}/{label}"], check=False)
        print(f"started {label}")
    if failures:
        return 1
    _wait_for_health(config)
    return 0


def _stop(config: dict[str, object], component: str) -> int:
    failures = 0
    for label, _ in _selected_plists(config, component):
        path = Path(config["launch_agent_dir"]) / f"{label}.plist"
        result = _launchctl(["bootout", _user_domain(), str(path)], check=False)
        if result.returncode != 0:
            failures += 1
            print(f"bootout {label}: {_first_line(result.stderr or result.stdout)}")
        else:
            print(f"stopped {label}")
    return 1 if failures else 0


def _status(config: dict[str, object]) -> int:
    for label in (APP_LABEL, OPENWEBUI_TUNNEL_LABEL):
        result = _launchctl(["print", f"{_user_domain()}/{label}"], check=False)
        state = "loaded" if result.returncode == 0 else "not loaded"
        print(f"{label}: {state}")
        if result.returncode == 0:
            for line in (result.stdout or "").splitlines():
                stripped = line.strip()
                if stripped.startswith(("pid =", "last exit code =", "state =")):
                    print(f"  {stripped}")
    print(f"local health: {'ok' if _http_ok(_local_base_url(config) + '/api/health') else 'warn'}")
    if str(config.get("remote_host") or "").strip():
        state = "ok" if _remote_http_ok(config, _remote_base_url(config) + "/api/health") else "warn"
        print(f"remote Open WebUI reverse health: {state}")
    else:
        print("remote Open WebUI reverse health: not configured")
    return 0


def _smoke_openwebui(
    config: dict[str, object],
    target: str,
    session_name: str,
    target_user_id: str,
    chat_prompt: str,
) -> int:
    token_file = Path(str(config["token_file"]))
    if not token_file.exists():
        print(f"missing token file: {token_file}", file=sys.stderr)
        return 2
    if target == "remote":
        return _smoke_openwebui_from_remote(config, token_file, session_name, target_user_id, chat_prompt)
    base_url = _local_base_url(config) if target == "local" else _remote_base_url(config)
    command = [
        str(config["python"]),
        "scripts/openwebui_bridge_smoke.py",
        "--base-url",
        base_url,
        "--token-file",
        str(token_file),
        "--session-name",
        session_name,
    ]
    if target_user_id:
        command.extend(["--target-user-id", target_user_id])
    if chat_prompt:
        command.extend(["--chat-prompt", chat_prompt])
    return _run(command, cwd=Path(config["repo_root"]), echo=True).returncode


def _smoke_openwebui_from_remote(
    config: dict[str, object],
    token_file: Path,
    session_name: str,
    target_user_id: str,
    chat_prompt: str,
) -> int:
    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        print(f"empty token file: {token_file}", file=sys.stderr)
        return 2
    payload = {
        "base_url": _remote_base_url(config),
        "token": token,
        "session_name": session_name,
        "target_user_id": target_user_id,
        "chat_prompt": chat_prompt,
    }
    remote_script = r"""
import json
import sys
from urllib import error, parse, request

cfg = json.loads(sys.stdin.read())
base_url = cfg["base_url"].rstrip("/")
token = cfg["token"]
target_user_id = cfg["target_user_id"]
session_name = cfg["session_name"]
chat_prompt = cfg["chat_prompt"]

def headers(auth=True):
    value = {"Accept": "application/json", "Content-Type": "application/json"}
    if auth:
        value["Authorization"] = "Bearer " + token
    return value

def read_json(req):
    try:
        with request.urlopen(req, timeout=20.0) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

def get(path, auth=True):
    return read_json(request.Request(base_url + path, headers=headers(auth), method="GET"))

def post(path, body):
    return read_json(
        request.Request(
            base_url + path,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers(True),
            method="POST",
        )
    )

failures = []
try:
    status = get("/api/openwebui/status", auth=False)
    print("status: object keys [" + ", ".join(sorted(status.keys())[:8]) + "]")
except Exception as exc:
    failures.append(f"status failed: {exc}")
try:
    spec = get("/api/openwebui/tools/openapi.json")
    paths = set((spec.get("paths") or {}).keys())
    required = {"/api/openwebui/stage/events", "/api/openwebui/chat", "/api/openwebui/sessions"}
    if not required.issubset(paths):
        failures.append("tool spec missing paths: " + ", ".join(sorted(required - paths)))
    print("tool spec paths: " + ", ".join(sorted(paths)))
except Exception as exc:
    failures.append(f"tool spec failed: {exc}")
try:
    query = "?target_user_id=" + parse.quote(target_user_id)
    sessions = get("/api/openwebui/sessions" + query)
    print("sessions visible: " + str(len(sessions) if isinstance(sessions, list) else "unknown"))
except Exception as exc:
    failures.append(f"sessions failed: {exc}")
try:
    event = post(
        "/api/openwebui/stage/events",
        {
            "session_name": session_name,
            "target_user_id": target_user_id,
            "text": "Open WebUI bridge smoke",
            "speaker": "Open WebUI Smoke",
        },
    )
    print("stage event: object keys [" + ", ".join(sorted(event.keys())[:8]) + "]")
except Exception as exc:
    failures.append(f"stage event failed: {exc}")
if chat_prompt:
    try:
        chat = post(
            "/api/openwebui/chat",
            {
                "session_name": session_name,
                "target_user_id": target_user_id,
                "prompt": chat_prompt,
            },
        )
        print("chat: object keys [" + ", ".join(sorted(chat.keys())[:8]) + "]")
    except Exception as exc:
        failures.append(f"chat failed: {exc}")
if failures:
    print("Open WebUI bridge smoke failed:", file=sys.stderr)
    for failure in failures:
        print("- " + failure, file=sys.stderr)
    sys.exit(1)
print("Open WebUI bridge smoke passed.")
"""
    result = subprocess.run(
        [
            str(config["ssh"]),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            str(config["remote_host"]),
            "python3 -c " + shlex.quote(remote_script),
        ],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def _wait_for_health(config: dict[str, object]) -> None:
    local_url = _local_base_url(config) + "/api/health"
    for _ in range(20):
        if _http_ok(local_url):
            print(f"local health ok: {local_url}")
            return
        time.sleep(0.5)
    print(f"local health not ready: {local_url}")


def _local_base_url(config: dict[str, object]) -> str:
    return f"http://{config['host']}:{config['port']}"


def _remote_base_url(config: dict[str, object]) -> str:
    return f"http://{config['remote_bind']}:{config['remote_port']}"


def _http_ok(url: str) -> bool:
    try:
        url = _validate_http_url(url)
        with request.urlopen(url, timeout=3.0) as response:  # nosec B310  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            return 200 <= response.status < 300
    except (OSError, error.URLError, error.HTTPError):
        return False


def _validate_http_url(url: str) -> str:
    parsed = parse.urlparse(str(url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be an absolute HTTP(S) URL")
    return parsed.geturl()


def _remote_http_ok(config: dict[str, object], url: str) -> bool:
    ssh = str(config["ssh"])
    if not str(config.get("remote_host") or "").strip():
        return False
    if not (shutil.which(ssh) or Path(ssh).exists()):
        return False
    result = _run(
        [
            ssh,
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            str(config["remote_host"]),
            "curl",
            "-fsS",
            url,
        ],
        check=False,
    )
    return result.returncode == 0


def _launchctl(args: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
    return _run(["launchctl", *args], check=check)


def _run(
    command: list[str],
    *,
    check: bool = False,
    cwd: Path | None = None,
    echo: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.stdout and echo:
        print(result.stdout, end="")
    if result.stderr and (check or echo):
        print(result.stderr, end="", file=sys.stderr)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, command)
    return result


def _user_domain() -> str:
    return f"gui/{os.getuid()}"


def _first_line(value: str) -> str:
    for line in value.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
