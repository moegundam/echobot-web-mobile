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
        "import sys\n"
        "from pathlib import Path\n"
        f"token_file = os.environ.get({TOKEN_FILE_ENV!r})\n"
        "token_file_value = None\n"
        "if token_file:\n"
        "    token_file_value = Path(token_file).read_text(encoding='utf-8')\n"
        "payload = {\n"
        "    'argv': sys.argv[1:],\n"
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
    repo_root = tmp_path / "workspace with spaces;$(not-executed)"
    repo_root.mkdir()
    token_file = tmp_path / "bridge-token"
    token_file.write_text("secret-token\n", encoding="utf-8")
    capture_path = tmp_path / "captured-environment.json"
    config = {
        "repo_root": repo_root,
        "host": "127.0.0.1;$(not-executed)",
        "port": 8001,
        "env_file": repo_root / '.env "quoted"',
        "channel_config": repo_root / "channels;$(not-executed).json",
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
    expected_arguments = [
        config["python"],
        "-m",
        "echobot",
        "app",
        "--host",
        str(config["host"]),
        "--port",
        str(config["port"]),
        "--workspace",
        str(repo_root),
        "--env-file",
        str(config["env_file"]),
        "--channel-config",
        str(config["channel_config"]),
    ]
    assert plist["ProgramArguments"] == expected_arguments
    assert plist["WorkingDirectory"] == str(repo_root)
    assert "/bin/zsh" not in expected_arguments
    assert "-lc" not in expected_arguments
    assert captured == {
        "argv": expected_arguments[1:],
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
    assert captured.pop("argv") == plist["ProgramArguments"][1:]
    assert captured == {
        "token": "direct-secret",
        "token_file": None,
        "token_file_value": None,
    }


def test_python_path_resolution_uses_absolute_discovered_executable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    entrypoint = _load_script("echobot_entrypoint")
    executable = tmp_path / "bin" / "python-local"
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.setattr(
        entrypoint.shutil,
        "which",
        lambda value: str(executable) if value == "python-local" else None,
    )

    resolved = entrypoint._resolve_python_path("python-local", tmp_path)

    assert resolved == executable.resolve()
    assert resolved.is_absolute()
    assert entrypoint._resolve_python_path(".venv/bin/python", tmp_path) == (
        tmp_path / ".venv" / "bin" / "python"
    ).resolve()


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


def test_doctor_reports_source_identity_with_git_output(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    entrypoint = _load_script("echobot_entrypoint")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    token_file = tmp_path / "bridge-token"
    token_file.write_text("token\n", encoding="utf-8")
    channel_config = repo_root / "channels.json"
    channel_config.write_text("{}", encoding="utf-8")

    git_result_map = {
        ("rev-parse", "--short", "HEAD"): "abcdef1",
        ("rev-parse", "--abbrev-ref", "HEAD"): "main",
        ("status", "--porcelain", "--untracked-files=normal"): "",
    }

    def fake_git_output(command: list[str], _repo_root: Path) -> str | None:
        return git_result_map.get(tuple(command))

    monkeypatch.setattr(entrypoint, "_git_output", fake_git_output)
    monkeypatch.setattr(entrypoint, "_http_ok", lambda _url: True)
    monkeypatch.setattr(entrypoint, "_remote_http_ok", lambda _config, _url: True)

    config = entrypoint._config_from_args(
        entrypoint.argparse.Namespace(
            repo_root=repo_root,
            host="127.0.0.1",
            port=8001,
            env_file=".env",
            channel_config="channels.json",
            token_file=str(token_file),
            remote_host="127.0.0.1",
            remote_bind="127.0.0.1",
            remote_port=18001,
            python=sys.executable,
            ssh="/bin/sh",
        )
    )
    (repo_root / ".venv" / "bin").mkdir(parents=True)

    assert entrypoint._doctor(config) == 0
    output = capsys.readouterr().out
    assert "source_identity: ok - " in output


def test_launchd_app_plist_includes_source_identity_environment(monkeypatch, tmp_path: Path) -> None:
    entrypoint = _load_script("echobot_entrypoint")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    token_file = tmp_path / "bridge-token"
    token_file.write_text("secret-token\n", encoding="utf-8")

    git_result_map = {
        ("rev-parse", "--short", "HEAD"): "a1b2c3d",
        ("rev-parse", "--abbrev-ref", "HEAD"): "feature/local-identity",
        ("status", "--porcelain", "--untracked-files=normal"): "",
    }

    def fake_git_output(command: list[str], _repo_root: Path) -> str | None:
        return git_result_map.get(tuple(command))

    monkeypatch.setattr(entrypoint, "_git_output", fake_git_output)

    config = {
        "repo_root": repo_root,
        "host": "127.0.0.1",
        "port": 8001,
        "env_file": repo_root / ".env",
        "channel_config": repo_root / ".echobot/channels.json",
        "token_file": str(token_file),
        "python": sys.executable,
    }

    plist = entrypoint._build_app_plist(config)
    identity = json.loads(plist["EnvironmentVariables"]["ECHOBOT_SOURCE_IDENTITY"])

    assert identity == {
        "version": "a1b2c3d",
        "branch": "feature/local-identity",
        "dirty": False,
        "checkout_status": "attached",
        "worktree_status": "clean",
    }


def test_launchd_app_plist_marks_source_identity_unknown_when_git_unavailable(monkeypatch, tmp_path: Path) -> None:
    entrypoint = _load_script("echobot_entrypoint")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    token_file = tmp_path / "bridge-token"
    token_file.write_text("secret-token\n", encoding="utf-8")

    monkeypatch.setattr(entrypoint, "_git_output", lambda _command, _repo_root: None)

    config = {
        "repo_root": repo_root,
        "host": "127.0.0.1",
        "port": 8001,
        "env_file": repo_root / ".env",
        "channel_config": repo_root / ".echobot/channels.json",
        "token_file": str(token_file),
        "python": sys.executable,
    }

    plist = entrypoint._build_app_plist(config)
    identity = json.loads(plist["EnvironmentVariables"]["ECHOBOT_SOURCE_IDENTITY"])

    assert identity == {
        "version": "unknown",
        "branch": "unknown",
        "dirty": "unknown",
        "checkout_status": "unknown",
        "worktree_status": "unknown",
    }
