#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test EchoBot Live2D catalog assets and stage event binding.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--session-name", default="live2d-smoke")
    parser.add_argument(
        "--selection-key",
        default="",
        help="Optional catalog selection_key. Defaults to the first model with expression and motion assets.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    try:
        live2d_payload = _request_json("GET", f"{base_url}/api/live2d-models")
        catalog = live2d_payload.get("catalog")
        if not isinstance(catalog, list) or not catalog:
            raise RuntimeError("Live2D catalog is empty")
        catalog_item = _select_catalog_item(catalog, args.selection_key)
        model_url = str(catalog_item.get("model_url") or "")
        if not model_url:
            raise RuntimeError("selected Live2D catalog item has no model_url")

        model = _request_json("GET", _absolute_url(base_url, model_url))
        file_refs = model.get("FileReferences")
        if not isinstance(file_refs, dict):
            raise RuntimeError("Live2D model3 JSON is missing FileReferences")
        asset_urls = _referenced_asset_urls(model_url, file_refs)
        for asset_url in asset_urls:
            _fetch_some_bytes(_absolute_url(base_url, asset_url))

        expression = _first_file(catalog_item.get("expressions"))
        motion = _first_file(catalog_item.get("motions"))
        if not motion:
            raise RuntimeError("selected Live2D model has no motion asset")

        _ensure_session(base_url, args.session_name)
        runtime_context = _request_json(
            "GET",
            f"{base_url}/api/sessions/{urllib.parse.quote(args.session_name, safe='')}/runtime-context",
        )
        stage_event = _request_json(
            "POST",
            f"{base_url}/api/stage/events",
            {
                "kind": "assistant_final",
                "session_name": args.session_name,
                "text": "Live2D asset smoke",
                "speaker": "Echo",
                "source": "live2d-smoke",
                "emotion": "asset_smoke",
                "expression": expression,
                "motion": motion,
            },
        )
        if stage_event.get("motion") != motion:
            raise RuntimeError("stage event did not preserve the requested motion")
        if expression and stage_event.get("expression") != expression:
            raise RuntimeError("stage event did not preserve the requested expression")

        print(
            "live2d asset smoke:",
            json.dumps(
                {
                    "selection_key": catalog_item.get("selection_key"),
                    "model_name": catalog_item.get("model_name"),
                    "model_url": model_url,
                    "checked_asset_count": len(asset_urls),
                    "expression": expression,
                    "motion": motion,
                    "runtime_session": runtime_context.get("session_name"),
                    "runtime_live2d_model": (
                        (runtime_context.get("live2d_model") or {}).get("model_name")
                        if isinstance(runtime_context.get("live2d_model"), dict)
                        else ""
                    ),
                },
                ensure_ascii=False,
            ),
        )
        print("Live2D asset smoke passed.")
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(
            f"Live2D asset smoke failed: HTTP {exc.code}: {detail}",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"Live2D asset smoke failed: {exc}", file=sys.stderr)
        return 1


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if payload is not None else {},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
    loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"expected JSON object from {url}")
    return loaded


def _fetch_some_bytes(url: str) -> None:
    with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=30) as response:
        sample = response.read(1)
    if not sample:
        raise RuntimeError(f"asset returned no bytes: {url}")


def _select_catalog_item(
    catalog: list[Any],
    requested_selection_key: str,
) -> dict[str, Any]:
    items = [item for item in catalog if isinstance(item, dict)]
    if requested_selection_key:
        for item in items:
            if str(item.get("selection_key") or "") == requested_selection_key:
                return item
        raise RuntimeError(f"Live2D selection_key not found: {requested_selection_key}")
    for item in items:
        if item.get("expressions") and item.get("motions"):
            return item
    for item in items:
        if item.get("motions"):
            return item
    return items[0]


def _referenced_asset_urls(model_url: str, file_refs: dict[str, Any]) -> list[str]:
    base_path = model_url.rsplit("/", 1)[0]
    urls: list[str] = []
    for key in ("Moc", "Physics", "Pose", "DisplayInfo"):
        value = str(file_refs.get(key) or "").strip()
        if value:
            urls.append(f"{base_path}/{value}")
    textures = file_refs.get("Textures")
    if isinstance(textures, list):
        for item in textures[:2]:
            value = str(item or "").strip()
            if value:
                urls.append(f"{base_path}/{value}")
    expressions = file_refs.get("Expressions")
    if isinstance(expressions, list):
        for item in expressions[:1]:
            if isinstance(item, dict):
                value = str(item.get("File") or "").strip()
                if value:
                    urls.append(f"{base_path}/{value}")
    motions = file_refs.get("Motions")
    if isinstance(motions, dict):
        for group in motions.values():
            if not isinstance(group, list) or not group:
                continue
            item = group[0]
            if isinstance(item, dict):
                value = str(item.get("File") or "").strip()
                if value:
                    urls.append(f"{base_path}/{value}")
                    break
    deduped: list[str] = []
    for url in urls:
        if url not in deduped:
            deduped.append(url)
    return deduped


def _first_file(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    for item in value:
        if isinstance(item, dict):
            file_name = str(item.get("file") or item.get("File") or "").strip()
            if file_name:
                return file_name
    return ""


def _ensure_session(base_url: str, session_name: str) -> None:
    try:
        _request_json(
            "POST",
            f"{base_url}/api/sessions",
            {
                "name": session_name,
                "route_mode": "chat_only",
            },
        )
    except urllib.error.HTTPError as exc:
        if exc.code not in {200, 400, 409}:
            raise
        detail = exc.read().decode("utf-8", errors="replace")
        if "already exists" not in detail.lower():
            raise


def _absolute_url(base_url: str, url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"{base_url}/{url.lstrip('/')}"


if __name__ == "__main__":
    raise SystemExit(main())
