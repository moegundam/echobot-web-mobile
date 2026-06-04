#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_HTTP_URL_SCHEMES = {"http", "https"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test EchoBot's Telegram gateway without printing secrets.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--session-name", default="telegram-smoke")
    parser.add_argument("--sender-id", default="")
    parser.add_argument("--chat-id", default="telegram-smoke-chat")
    parser.add_argument("--text", default="/ping telegram-ok")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--require-poller-running",
        action="store_true",
        help="Fail when the Telegram poller is not running.",
    )
    parser.add_argument(
        "--skip-stage-sse",
        action="store_true",
        help="Skip the SSE replay check for the mirrored Stage event.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    try:
        _request_json("GET", f"{base_url}/api/health")
        config = _request_json("GET", f"{base_url}/api/channels/config")
        status = _request_json("GET", f"{base_url}/api/channels/status")
        telegram_config = config.get("telegram") if isinstance(config, dict) else {}
        telegram_status = status.get("telegram") if isinstance(status, dict) else {}
        if not isinstance(telegram_config, dict):
            telegram_config = {}
        if not isinstance(telegram_status, dict):
            telegram_status = {}

        enabled = bool(telegram_config.get("enabled") or telegram_status.get("enabled"))
        running = bool(telegram_status.get("running"))
        configured = bool(telegram_config.get("bot_token_configured"))
        allow_from = [
            str(item)
            for item in (telegram_config.get("allow_from") or [])
            if str(item).strip()
        ]
        sender_id = args.sender_id.strip() or _default_sender(allow_from)

        print(
            "telegram config:",
            json.dumps(
                {
                    "enabled": enabled,
                    "running": running,
                    "configured": configured,
                    "bot_token_configured": bool(telegram_config.get("bot_token_configured")),
                    "allow_from_count": len(allow_from),
                    "mirror_to_stage": bool(telegram_config.get("mirror_to_stage")),
                },
                ensure_ascii=False,
            ),
        )
        if args.require_poller_running and not running:
            print("Telegram poller is not running", file=sys.stderr)
            return 2

        _ensure_session(base_url, args.session_name)
        accepted = _request_json(
            "POST",
            f"{base_url}/api/channels/telegram/local-test-message",
            {
                "chat_id": args.chat_id,
                "sender_id": sender_id,
                "text": args.text,
                "session_name": args.session_name,
            },
        )
        print(
            "local inbound accepted:",
            json.dumps(
                {
                    "accepted": bool(accepted.get("accepted")),
                    "channel": accepted.get("channel"),
                    "session_name": accepted.get("session_name"),
                    "external_delivery": bool(accepted.get("external_delivery")),
                },
                ensure_ascii=False,
            ),
        )
        if _is_gateway_smoke_command(args.text):
            print("session history: skipped for deterministic gateway command")
        else:
            _wait_for_assistant_history(base_url, args.session_name, args.timeout)
        if not args.skip_stage_sse:
            _read_stage_event_replay(base_url, args.session_name)
        if not running:
            print(
                "native delivery not verified: configure a repo-external Telegram bot token "
                "and restart EchoBot.",
            )
        print("Telegram gateway smoke passed.")
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(
            f"Telegram gateway smoke failed: HTTP {exc.code}: {detail}",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"Telegram gateway smoke failed: {exc}", file=sys.stderr)
        return 1


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = _validate_http_url(url)
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if payload is not None else {},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=180) as response:  # nosec B310  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        raw = response.read().decode("utf-8")
    if not raw:
        return {}
    loaded = json.loads(raw)
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _ensure_session(base_url: str, session_name: str) -> None:
    try:
        _request_json(
            "POST",
            f"{base_url}/api/sessions",
            {
                "name": session_name,
                "channel_type": "telegram",
                "channel_integration_id": "telegram",
                "route_mode": "chat_only",
            },
        )
    except urllib.error.HTTPError as exc:
        if exc.code not in {200, 400, 409}:
            raise
        detail = exc.read().decode("utf-8", errors="replace")
        if "already exists" not in detail.lower():
            raise


def _wait_for_assistant_history(base_url: str, session_name: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    encoded_session = urllib.parse.quote(session_name, safe="")
    while time.monotonic() < deadline:
        detail = _request_json("GET", f"{base_url}/api/sessions/{encoded_session}")
        history = detail.get("history")
        if isinstance(history, list) and len(history) >= 2:
            roles = [str(item.get("role") or "") for item in history if isinstance(item, dict)]
            if "user" in roles and "assistant" in roles:
                print(
                    "session history:",
                    json.dumps(
                        {
                            "message_count": len(history),
                            "has_user": True,
                            "has_assistant": True,
                        },
                        ensure_ascii=False,
                    ),
                )
                return
        time.sleep(1.0)
    raise TimeoutError("timed out waiting for assistant response in session history")


def _read_stage_event_replay(base_url: str, session_name: str) -> None:
    encoded_session = urllib.parse.quote(session_name, safe="")
    url = _validate_http_url(f"{base_url}/api/stage/events?session_name={encoded_session}")
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload = json.loads(line.split(":", 1)[1].strip())
            if payload.get("kind") == "assistant_final":
                print(
                    "stage replay:",
                    json.dumps(
                        {
                            "kind": payload.get("kind"),
                            "source": payload.get("source"),
                            "session_name": payload.get("session_name"),
                        },
                        ensure_ascii=False,
                    ),
                )
                return
    raise TimeoutError("timed out waiting for mirrored stage event replay")


def _validate_http_url(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.scheme.lower() not in _HTTP_URL_SCHEMES or not parsed.netloc:
        raise ValueError("smoke-test URL must be an absolute HTTP(S) URL")
    return parsed.geturl()


def _default_sender(allow_from: list[str]) -> str:
    if not allow_from or "*" in allow_from:
        return "local-telegram-user"
    return allow_from[0]


def _is_gateway_smoke_command(text: str) -> bool:
    command = str(text or "").strip().split(maxsplit=1)[0].split("@", 1)[0].lower()
    return command in {"/ping", "/smoke"}


if __name__ == "__main__":
    raise SystemExit(main())
