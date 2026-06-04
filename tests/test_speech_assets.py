from __future__ import annotations

import io
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import echobot.speech_assets as speech_assets


class FakeDownloadResponse:
    def __init__(
        self,
        chunks: list[bytes],
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._chunks = list(chunks)
        self.headers = headers or {}

    def __enter__(self) -> FakeDownloadResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, _chunk_size: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class SpeechAssetsTests(unittest.TestCase):
    def test_validate_http_url_rejects_private_targets_by_default(self) -> None:
        blocked_urls = [
            "http://127.0.0.1:8000/model.bin",
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost:8000/model.bin",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://printer.local/model.bin",
            "http://intranet/model.bin",
        ]

        for url in blocked_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    speech_assets.validate_http_url(url)

    def test_validate_http_url_rejects_dns_names_that_resolve_private(self) -> None:
        private_result = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("127.0.0.1", 80),
            )
        ]

        with patch("echobot.speech_assets.socket.getaddrinfo", return_value=private_result):
            with self.assertRaises(ValueError):
                speech_assets.validate_http_url("https://public-name.example/model.bin")

    def test_validate_http_url_rejects_unresolvable_dns_names(self) -> None:
        with patch(
            "echobot.speech_assets.socket.getaddrinfo",
            side_effect=socket.gaierror,
        ):
            with self.assertRaises(ValueError):
                speech_assets.validate_http_url("https://missing-name.example/model.bin")

    def test_validate_http_url_allows_dns_names_that_resolve_public(self) -> None:
        public_result = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", 443),
            )
        ]

        with patch("echobot.speech_assets.socket.getaddrinfo", return_value=public_result):
            self.assertEqual(
                "https://example.com/model.bin",
                speech_assets.validate_http_url("https://example.com/model.bin"),
            )

    def test_validate_http_url_allows_private_targets_when_explicit(self) -> None:
        self.assertEqual(
            "http://127.0.0.1:8000/v1",
            speech_assets.validate_http_url(
                "http://127.0.0.1:8000/v1",
                allow_private=True,
            ),
        )

    def test_download_file_prints_progress_with_known_size(self) -> None:
        response = FakeDownloadResponse(
            [b"ab", b"cdef", b""],
            headers={"Content-Length": "6"},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "model.bin"
            stderr = io.StringIO()

            with patch("echobot.speech_assets.urlopen", return_value=response):
                with patch("echobot.speech_assets._hostname_resolves_to_private_address", return_value=False):
                    with patch("sys.stderr", stderr):
                        speech_assets.download_file(
                            "https://example.com/model.bin",
                            destination,
                            timeout_seconds=1.0,
                            progress_label="Test model",
                        )

            output = stderr.getvalue()
            downloaded_bytes = destination.read_bytes()

        self.assertEqual(b"abcdef", downloaded_bytes)
        self.assertIn("[download] Test model: starting", output)
        self.assertIn("100.0%", output)
        self.assertIn("completed", output)

    def test_download_file_prints_progress_when_size_is_unknown(self) -> None:
        response = FakeDownloadResponse([b"abc", b"def", b""])

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "model.bin"
            stderr = io.StringIO()

            with patch("echobot.speech_assets.urlopen", return_value=response):
                with patch("echobot.speech_assets._hostname_resolves_to_private_address", return_value=False):
                    with patch("echobot.speech_assets._DOWNLOAD_PROGRESS_UPDATE_INTERVAL_SECONDS", 0.0):
                        with patch("sys.stderr", stderr):
                            speech_assets.download_file(
                                "https://example.com/model.bin",
                                destination,
                                timeout_seconds=1.0,
                                progress_label="Unknown model",
                            )

            output = stderr.getvalue()
            downloaded_bytes = destination.read_bytes()

        self.assertEqual(b"abcdef", downloaded_bytes)
        self.assertIn("size unknown", output)
        self.assertIn("downloaded", output)
        self.assertIn("completed", output)
