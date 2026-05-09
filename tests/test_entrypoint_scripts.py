from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_launchd_app_plist_uses_token_file_not_token_value(tmp_path: Path) -> None:
    entrypoint = _load_script("echobot_entrypoint")
    token_file = tmp_path / "bridge-token"
    token_file.write_text("secret-token\n", encoding="utf-8")
    config = {
        "repo_root": ROOT,
        "host": "127.0.0.1",
        "port": 8001,
        "env_file": ".env",
        "channel_config": ".echobot/channels.json",
        "token_file": str(token_file),
        "python": str(ROOT / ".venv" / "bin" / "python"),
    }

    plist = entrypoint._build_app_plist(config)
    rendered = repr(plist)

    assert plist["Label"] == entrypoint.APP_LABEL
    assert "ECHOBOT_OPENWEBUI_BRIDGE_TOKEN_FILE" in rendered
    assert str(token_file) in rendered
    assert "secret-token" not in rendered
    assert "-m echobot app" in rendered


def test_launchd_gb10_tunnel_plist_maps_remote_to_local_port() -> None:
    entrypoint = _load_script("echobot_entrypoint")
    config = {
        "ssh": "/usr/bin/ssh",
        "remote_bind": "127.0.0.1",
        "remote_port": 18001,
        "host": "127.0.0.1",
        "port": 8001,
        "remote_host": "fortune@gx10-6703.local",
    }

    plist = entrypoint._build_gb10_tunnel_plist(config)

    assert plist["Label"] == entrypoint.GB10_TUNNEL_LABEL
    assert "127.0.0.1:18001:127.0.0.1:8001" in plist["ProgramArguments"]
    assert "fortune@gx10-6703.local" in plist["ProgramArguments"]
