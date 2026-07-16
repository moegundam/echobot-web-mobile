from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from threading import Event, Lock, Thread
from time import sleep
from typing import Iterator

import httpx


DEFAULT_API_BODY_LIMIT_BYTES = 2 * 1024 * 1024
ALLOWED_MULTIPART_BYTES = 3 * 1024 * 1024
IDENTITY_HEADER = {"Cf-Access-Authenticated-User-Email": "ingress-smoke@example.test"}


@dataclass
class MockUpstreamState:
    upstream_hits: Counter[str] = field(default_factory=Counter)
    lock: Lock = field(default_factory=Lock)
    stream_release: Event = field(default_factory=Event)

    def record(self, method: str, path: str) -> None:
        with self.lock:
            self.upstream_hits[f"{method} {path}"] += 1

    def snapshot(self) -> dict[str, int]:
        with self.lock:
            return dict(sorted(self.upstream_hits.items()))


def _handler_for(state: MockUpstreamState):
    class MockUpstreamHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            state.record("GET", path)
            if path == "/api/stage/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(b"event: ready\ndata: {}\n\n")
                self.wfile.flush()
                state.stream_release.wait(timeout=20.0)
                return
            payload = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            state.record("POST", path)
            content_length = int(self.headers.get("Content-Length") or "0")
            remaining = content_length
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 1024 * 1024))
                if not chunk:
                    break
                remaining -= len(chunk)
            payload = b'{"accepted":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return MockUpstreamHandler


@contextmanager
def _managed_mock_upstream(port: int) -> Iterator[MockUpstreamState]:
    state = MockUpstreamState()
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler_for(state))
    thread = Thread(target=server.serve_forever, name="echobot-ingress-mock", daemon=True)
    thread.start()
    try:
        yield state
    finally:
        state.stream_release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


def _request_status(
    method: str,
    url: str,
    *,
    content: bytes | Iterator[bytes] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> int:
    try:
        response = httpx.request(
            method,
            url,
            content=content,
            headers={**IDENTITY_HEADER, **(headers or {})},
            timeout=timeout,
            trust_env=False,
        )
    except httpx.HTTPError:
        return -1
    return response.status_code


def _rate_statuses(base_url: str, request_count: int, workers: int) -> list[int]:
    url = f"{base_url.rstrip('/')}/api/health"
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda _: _request_status("GET", url, timeout=10.0),
                range(request_count),
            )
        )


def _stream_statuses(
    base_url: str,
    *,
    mock_state: MockUpstreamState | None = None,
    connection_limit: int = 4,
) -> list[int]:
    url = f"{base_url.rstrip('/')}/api/stage/events?session_name=ingress-smoke"
    release = Event()
    observed: Queue[int] = Queue()

    def hold_stream() -> None:
        try:
            timeout = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
            with httpx.stream(
                "GET",
                url,
                headers=IDENTITY_HEADER,
                timeout=timeout,
                trust_env=False,
            ) as response:
                observed.put(response.status_code)
                if response.status_code == 200:
                    release.wait(timeout=15.0)
        except httpx.HTTPError:
            observed.put(-1)

    statuses: list[int] = []
    with ThreadPoolExecutor(max_workers=connection_limit + 1) as executor:
        futures = []
        try:
            for _ in range(connection_limit):
                futures.append(executor.submit(hold_stream))
                statuses.append(observed.get(timeout=10.0))
                sleep(0.6)
            futures.append(executor.submit(hold_stream))
            statuses.append(observed.get(timeout=10.0))
        finally:
            release.set()
            if mock_state is not None:
                mock_state.stream_release.set()
            for future in futures:
                future.result(timeout=15.0)
    return statuses


def _assert_no_transport_failures(label: str, statuses: list[int]) -> None:
    if any(status <= 0 for status in statuses):
        raise RuntimeError(f"{label} produced a transport failure: {statuses}")


def _run_probes(
    *,
    base_url: str,
    body_limit_bytes: int,
    rate_requests: int,
    rate_workers: int,
    mock_state: MockUpstreamState | None,
) -> dict[str, object]:
    normalized_base_url = base_url.rstrip("/")
    health_status = _request_status("GET", f"{normalized_base_url}/healthz")
    if health_status != 200:
        raise RuntimeError(f"Ingress health check returned {health_status}, expected 200")

    before_oversized = mock_state.snapshot() if mock_state is not None else {}
    oversized_payload = b"x" * (body_limit_bytes + 1)
    oversized_status = _request_status(
        "POST",
        f"{normalized_base_url}/api/stage/events",
        content=oversized_payload,
        headers={"Content-Type": "application/json"},
        timeout=30.0,
    )
    if oversized_status != 413:
        raise RuntimeError(
            f"Oversized request returned {oversized_status}, expected ingress 413",
        )
    if mock_state is not None and mock_state.snapshot() != before_oversized:
        raise RuntimeError("Oversized request reached the mock upstream")

    before_chunked = mock_state.snapshot() if mock_state is not None else {}
    oversized_chunked_status = _request_status(
        "POST",
        f"{normalized_base_url}/api/stage/events",
        content=iter((b"x" * (512 * 1024) for _ in range(5))),
        headers={"Content-Type": "application/octet-stream"},
        timeout=30.0,
    )
    if oversized_chunked_status != 413:
        raise RuntimeError(
            "Oversized chunked request returned "
            f"{oversized_chunked_status}, expected ingress 413",
        )
    if mock_state is not None and mock_state.snapshot() != before_chunked:
        raise RuntimeError("Oversized chunked request reached the mock upstream")

    with httpx.Client(timeout=30.0, trust_env=False, headers=IDENTITY_HEADER) as client:
        allowed_multipart = client.post(
            f"{normalized_base_url}/api/attachments/files",
            files={"file": ("allowed.bin", b"a" * ALLOWED_MULTIPART_BYTES)},
        )
    if allowed_multipart.status_code != 200:
        raise RuntimeError(
            "Allowed multipart request returned "
            f"{allowed_multipart.status_code}, expected 200",
        )
    if mock_state is not None:
        hits = mock_state.snapshot()
        if hits.get("POST /api/attachments/files") != 1:
            raise RuntimeError("Allowed multipart request did not reach the mock upstream once")

    stream_statuses = _stream_statuses(
        normalized_base_url,
        mock_state=mock_state,
    )
    _assert_no_transport_failures("Connection probe", stream_statuses)
    if stream_statuses.count(200) < 4 or 429 not in stream_statuses:
        raise RuntimeError(
            f"Connection probe returned {stream_statuses}; expected four streams and a 429",
        )

    statuses = _rate_statuses(normalized_base_url, rate_requests, rate_workers)
    _assert_no_transport_failures("Rate probe", statuses)
    status_counts = Counter(statuses)
    if status_counts[429] == 0:
        raise RuntimeError(
            "Rate probe did not receive 429; ingress rate limiting is not proven",
        )
    server_errors = sum(count for status, count in status_counts.items() if status >= 500)
    if server_errors:
        raise RuntimeError(f"Rate probe produced {server_errors} server errors")

    return {
        "health_status": health_status,
        "oversized_status": oversized_status,
        "oversized_chunked_status": oversized_chunked_status,
        "allowed_multipart_status": allowed_multipart.status_code,
        "stream_status_counts": dict(sorted(Counter(stream_statuses).items())),
        "rate_status_counts": dict(sorted(status_counts.items())),
        "upstream_hits": mock_state.snapshot() if mock_state is not None else {},
    }


def run(
    *,
    base_url: str,
    body_limit_bytes: int = DEFAULT_API_BODY_LIMIT_BYTES,
    rate_requests: int = 96,
    rate_workers: int = 32,
    manage_mock_upstream: bool = False,
    mock_upstream_port: int = 8000,
) -> dict[str, object]:
    if manage_mock_upstream:
        with _managed_mock_upstream(mock_upstream_port) as mock_state:
            return _run_probes(
                base_url=base_url,
                body_limit_bytes=body_limit_bytes,
                rate_requests=rate_requests,
                rate_workers=rate_workers,
                mock_state=mock_state,
            )
    return _run_probes(
        base_url=base_url,
        body_limit_bytes=body_limit_bytes,
        rate_requests=rate_requests,
        rate_workers=rate_workers,
        mock_state=None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify EchoBot ingress upload, rate, and connection limits.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--body-limit-bytes",
        type=int,
        default=DEFAULT_API_BODY_LIMIT_BYTES,
    )
    parser.add_argument("--rate-requests", type=int, default=96)
    parser.add_argument("--rate-workers", type=int, default=32)
    parser.add_argument("--manage-mock-upstream", action="store_true")
    parser.add_argument("--mock-upstream-port", type=int, default=8000)
    args = parser.parse_args()

    result = run(
        base_url=args.base_url,
        body_limit_bytes=max(args.body_limit_bytes, 1),
        rate_requests=max(args.rate_requests, 1),
        rate_workers=max(args.rate_workers, 1),
        manage_mock_upstream=args.manage_mock_upstream,
        mock_upstream_port=args.mock_upstream_port,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
