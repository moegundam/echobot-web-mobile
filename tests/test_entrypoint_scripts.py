from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKEN_ENV = "ECHOBOT_OPENWEBUI_BRIDGE_TOKEN"
TOKEN_FILE_ENV = "ECHOBOT_OPENWEBUI_BRIDGE_TOKEN_FILE"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_environment_capture_python(tmp_path: Path) -> Path:
    capture_python = tmp_path / "capture_environment.py"
    capture_python.write_text(
        f"#!{sys.executable}\n"
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        f"token_file = os.environ.get({TOKEN_FILE_ENV!r})\n"
        "token_file_value = None\n"
        "if token_file:\n"
        "    token_file_value = Path(token_file).read_text(encoding='utf-8')\n"
        "payload = {\n"
        f"    'token': os.environ.get({TOKEN_ENV!r}),\n"
        "    'token_file': token_file,\n"
        "    'token_file_value': token_file_value,\n"
        "}\n"
        "Path(os.environ['ECHOBOT_ENTRYPOINT_TEST_CAPTURE']).write_text(\n"
        "    json.dumps(payload, ensure_ascii=False),\n"
        "    encoding='utf-8',\n"
        ")\n",
        encoding="utf-8",
    )
    capture_python.chmod(0o700)
    return capture_python


def _run_app_command(
    plist: dict[str, object],
    capture_path: Path,
    extra_environment: dict[str, str] | None = None,
) -> dict[str, object]:
    environment = dict(plist["EnvironmentVariables"])
    environment["ECHOBOT_ENTRYPOINT_TEST_CAPTURE"] = str(capture_path)
    environment.update(extra_environment or {})
    result = subprocess.run(
        plist["ProgramArguments"],
        cwd=plist["WorkingDirectory"],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(capture_path.read_text(encoding="utf-8"))


def test_openwebui_smoke_reads_token_file_without_echoing_secret(tmp_path: Path) -> None:
    smoke = _load_script("openwebui_bridge_smoke")
    token_file = tmp_path / "bridge-token"
    token_file.write_text("secret-token\n", encoding="utf-8")

    assert smoke._read_token("", str(token_file)) == "secret-token"
    assert smoke._read_token("explicit-token", str(token_file)) == "explicit-token"


def test_telegram_smoke_default_sender_respects_allowlist() -> None:
    smoke = _load_script("telegram_gateway_smoke")

    assert smoke._default_sender([]) == "local-telegram-user"
    assert smoke._default_sender(["*"]) == "local-telegram-user"
    assert smoke._default_sender(["12345"]) == "12345"


def test_gateway_smoke_scripts_detect_deterministic_commands() -> None:
    telegram = _load_script("telegram_gateway_smoke")
    discord = _load_script("discord_gateway_smoke")

    for smoke in (telegram, discord):
        assert smoke._is_gateway_smoke_command("/ping OK")
        assert smoke._is_gateway_smoke_command("/ping@EchoBot OK")
        assert smoke._is_gateway_smoke_command("/smoke OK")
        assert not smoke._is_gateway_smoke_command("Reply exactly: OK")


def test_launchd_app_plist_leaves_file_token_for_application_to_read(tmp_path: Path) -> None:
    entrypoint = _load_script("echobot_entrypoint")
    token_file = tmp_path / "bridge-token"
    token_file.write_text("secret-token\n", encoding="utf-8")
    capture_path = tmp_path / "captured-environment.json"
    config = {
        "repo_root": ROOT,
        "host": "127.0.0.1",
        "port": 8001,
        "env_file": ".env",
        "channel_config": ".echobot/channels.json",
        "token_file": str(token_file),
        "python": str(_write_environment_capture_python(tmp_path)),
    }

    plist = entrypoint._build_app_plist(config)
    rendered = repr(plist)
    captured = _run_app_command(plist, capture_path)

    assert plist["Label"] == entrypoint.APP_LABEL
    assert plist["EnvironmentVariables"][TOKEN_FILE_ENV] == str(token_file)
    assert TOKEN_ENV not in plist["EnvironmentVariables"]
    assert str(token_file) in rendered
    assert "secret-token" not in rendered
    assert "-m echobot app" in rendered
    assert captured == {
        "token": None,
        "token_file": str(token_file),
        "token_file_value": "secret-token\n",
    }


def test_launchd_app_plist_preserves_direct_token_without_file_source(tmp_path: Path) -> None:
    entrypoint = _load_script("echobot_entrypoint")
    capture_path = tmp_path / "captured-environment.json"
    config = {
        "repo_root": ROOT,
        "host": "127.0.0.1",
        "port": 8001,
        "env_file": ".env",
        "channel_config": ".echobot/channels.json",
        "token_file": "",
        "python": str(_write_environment_capture_python(tmp_path)),
    }

    plist = entrypoint._build_app_plist(config)
    captured = _run_app_command(
        plist,
        capture_path,
        {TOKEN_ENV: "direct-secret"},
    )

    assert TOKEN_FILE_ENV not in plist["EnvironmentVariables"]
    assert captured == {
        "token": "direct-secret",
        "token_file": None,
        "token_file_value": None,
    }


def test_launchd_openwebui_tunnel_plist_maps_remote_to_local_port() -> None:
    entrypoint = _load_script("echobot_entrypoint")
    config = {
        "ssh": "/usr/bin/ssh",
        "remote_bind": "127.0.0.1",
        "remote_port": 18001,
        "host": "127.0.0.1",
        "port": 8001,
        "remote_host": "user@openwebui-host.local",
    }

    plist = entrypoint._build_openwebui_tunnel_plist(config)

    assert plist["Label"] == entrypoint.OPENWEBUI_TUNNEL_LABEL
    assert "127.0.0.1:18001:127.0.0.1:8001" in plist["ProgramArguments"]
    assert "user@openwebui-host.local" in plist["ProgramArguments"]
