from __future__ import annotations

import argparse
import json
import os
import sys
from urllib import error, parse, request


TOKEN_ENV = "ECHOBOT_OPENWEBUI_BRIDGE_TOKEN"
TOKEN_FILE_ENV = "ECHOBOT_OPENWEBUI_BRIDGE_TOKEN_FILE"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test EchoBot's Open WebUI bridge API surface.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--token", default=os.environ.get(TOKEN_ENV, ""))
    parser.add_argument(
        "--token-file",
        default=os.environ.get(TOKEN_FILE_ENV, ""),
        help=(
            "Read the bridge bearer token from a local runtime-only file. "
            f"Defaults to {TOKEN_FILE_ENV} when set."
        ),
    )
    parser.add_argument("--session-name", default="openwebui-smoke")
    parser.add_argument("--target-user-id", default="")
    parser.add_argument("--chat-prompt", default="")
    args = parser.parse_args()

    token = _read_token(args.token, args.token_file)
    if not token:
        print(
            f"Missing bridge token. Set {TOKEN_ENV}, pass --token, or pass --token-file.",
            file=sys.stderr,
        )
        return 2

    base_url = str(args.base_url).rstrip("/")
    target_user_id = str(args.target_user_id or "").strip()
    failures: list[str] = []

    try:
        status = _get_json(f"{base_url}/api/openwebui/status")
        print(_summary("status", status))
    except Exception as exc:
        failures.append(f"status failed: {exc}")

    try:
        spec = _get_json(
            f"{base_url}/api/openwebui/tools/openapi.json",
            token=token,
        )
        paths = sorted((spec.get("paths") or {}).keys())
        required_paths = {
            "/api/openwebui/stage/events",
            "/api/openwebui/chat",
            "/api/openwebui/sessions",
        }
        if not required_paths.issubset(paths):
            failures.append(f"tool spec missing paths: {sorted(required_paths - set(paths))}")
        print(f"tool spec paths: {', '.join(paths)}")
    except Exception as exc:
        failures.append(f"tool spec failed: {exc}")

    query = ""
    if target_user_id:
        query = "?" + parse.urlencode({"target_user_id": target_user_id})
    try:
        sessions = _get_json(
            f"{base_url}/api/openwebui/sessions{query}",
            token=token,
        )
        print(f"sessions visible: {len(sessions) if isinstance(sessions, list) else 'unknown'}")
    except Exception as exc:
        failures.append(f"sessions failed: {exc}")

    stage_payload = {
        "session_name": args.session_name,
        "text": "Open WebUI bridge smoke",
        "speaker": "Open WebUI Smoke",
    }
    if target_user_id:
        stage_payload["target_user_id"] = target_user_id
    try:
        event = _post_json(
            f"{base_url}/api/openwebui/stage/events",
            stage_payload,
            token=token,
        )
        print(_summary("stage event", event))
    except Exception as exc:
        failures.append(f"stage event failed: {exc}")

    if args.chat_prompt:
        chat_payload = {
            "session_name": args.session_name,
            "prompt": args.chat_prompt,
        }
        if target_user_id:
            chat_payload["target_user_id"] = target_user_id
        try:
            chat = _post_json(
                f"{base_url}/api/openwebui/chat",
                chat_payload,
                token=token,
            )
            print(_summary("chat", chat))
        except Exception as exc:
            failures.append(f"chat failed: {exc}")

    if failures:
        print("Open WebUI bridge smoke failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Open WebUI bridge smoke passed.")
    return 0


def _headers(token: str = "") -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _read_token(raw_token: str = "", token_file: str = "") -> str:
    token = str(raw_token or "").strip()
    if token:
        return token
    token_file_path = str(token_file or "").strip()
    if not token_file_path:
        return ""
    try:
        with open(token_file_path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError as exc:
        raise RuntimeError(f"Could not read token file: {exc}") from exc


def _get_json(url: str, *, token: str = ""):
    url = _validate_http_url(url)
    http_request = request.Request(url, headers=_headers(token), method="GET")
    return _read_json(http_request)


def _post_json(url: str, payload: dict[str, object], *, token: str):
    url = _validate_http_url(url)
    http_request = request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_headers(token),
        method="POST",
    )
    return _read_json(http_request)


def _read_json(http_request: request.Request):
    try:
        with request.urlopen(http_request, timeout=20.0) as response:  # nosec B310  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _validate_http_url(url: str) -> str:
    parsed = parse.urlparse(str(url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("smoke-test URL must be an absolute HTTP(S) URL")
    return parsed.geturl()


def _summary(label: str, payload) -> str:
    if isinstance(payload, dict):
        keys = ", ".join(sorted(payload.keys())[:8])
        return f"{label}: object keys [{keys}]"
    return f"{label}: {type(payload).__name__}"


if __name__ == "__main__":
    raise SystemExit(main())
