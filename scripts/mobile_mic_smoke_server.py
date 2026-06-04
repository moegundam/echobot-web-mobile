from __future__ import annotations

import argparse
import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, parse, request


MAX_AUDIO_BYTES = 12 * 1024 * 1024

LAST_RESULT: dict[str, object] = {
    "status": "waiting",
    "updated_at": None,
    "result": None,
    "error": None,
}


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EchoBot Mobile Mic Smoke</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, -apple-system, sans-serif; }
    body { margin: 0; padding: 24px; min-height: 100dvh; display: grid; place-items: center; }
    main { width: min(100%, 520px); display: grid; gap: 18px; }
    button { min-height: 52px; border-radius: 12px; border: 1px solid #8886; font-size: 18px; font-weight: 700; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; padding: 14px; border-radius: 10px; background: #8882; }
  </style>
</head>
<body>
  <main>
    <h1>EchoBot Mobile Mic Smoke</h1>
    <p>Tap Start, allow microphone access, and say a short sentence for two seconds.</p>
    <button id="start">Start 2s mic test</button>
    <pre id="status">Waiting.</pre>
  </main>
  <script>
    const statusBox = document.getElementById("status");
    const startButton = document.getElementById("start");

    function setStatus(value) {
      statusBox.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    }

    function mergeBuffers(chunks, length) {
      const merged = new Float32Array(length);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }
      return merged;
    }

    function encodeWav(samples, sampleRate) {
      const buffer = new ArrayBuffer(44 + samples.length * 2);
      const view = new DataView(buffer);
      const writeString = (offset, text) => {
        for (let index = 0; index < text.length; index += 1) {
          view.setUint8(offset + index, text.charCodeAt(index));
        }
      };
      writeString(0, "RIFF");
      view.setUint32(4, 36 + samples.length * 2, true);
      writeString(8, "WAVE");
      writeString(12, "fmt ");
      view.setUint32(16, 16, true);
      view.setUint16(20, 1, true);
      view.setUint16(22, 1, true);
      view.setUint32(24, sampleRate, true);
      view.setUint32(28, sampleRate * 2, true);
      view.setUint16(32, 2, true);
      view.setUint16(34, 16, true);
      writeString(36, "data");
      view.setUint32(40, samples.length * 2, true);
      let offset = 44;
      for (const sample of samples) {
        const clamped = Math.max(-1, Math.min(1, sample));
        view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
        offset += 2;
      }
      return new Blob([view], { type: "audio/wav" });
    }

    async function recordWav(durationMs) {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
      const audioContext = new AudioContextCtor();
      await audioContext.resume();
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      const chunks = [];
      let totalLength = 0;
      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        chunks.push(new Float32Array(input));
        totalLength += input.length;
      };
      source.connect(processor);
      processor.connect(audioContext.destination);
      await new Promise((resolve) => setTimeout(resolve, durationMs));
      processor.disconnect();
      source.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      const sampleRate = audioContext.sampleRate;
      await audioContext.close();
      return encodeWav(mergeBuffers(chunks, totalLength), sampleRate);
    }

    startButton.addEventListener("click", async () => {
      startButton.disabled = true;
      try {
        if (!window.isSecureContext) {
          throw new Error("This page is not a secure context.");
        }
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error("getUserMedia is unavailable.");
        }
        setStatus("Recording for 2 seconds...");
        const wav = await recordWav(2200);
        setStatus(`Uploading ${wav.size} bytes...`);
        const response = await fetch("/api/mic-test", {
          method: "POST",
          headers: { "Content-Type": "audio/wav" },
          body: wav,
        });
        const payload = await response.json();
        setStatus(payload);
      } catch (error) {
        setStatus({ status: "failed", error: `${error.name || "Error"}: ${error.message || error}` });
      } finally {
        startButton.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


class MicSmokeHandler(BaseHTTPRequestHandler):
    echobot_base_url = "http://127.0.0.1:8000"

    def do_GET(self) -> None:
        if self.path == "/":
            self._send_bytes(HTTPStatus.OK, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/api/health":
            self._send_json({"status": "ok", "echobot_base_url": self.echobot_base_url})
            return
        if self.path == "/api/results":
            self._send_json(LAST_RESULT)
            return
        self._send_json({"status": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/api/mic-test":
            self._send_json({"status": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("content-length", "0") or "0")
        if content_length <= 0:
            self._store_result("failed", error="empty audio body")
            self._send_json(LAST_RESULT, status=HTTPStatus.BAD_REQUEST)
            return
        if content_length > MAX_AUDIO_BYTES:
            self._store_result("failed", error="audio body is too large")
            self._send_json(LAST_RESULT, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return

        audio_bytes = self.rfile.read(content_length)
        try:
            asr_payload = self._forward_to_asr(audio_bytes)
        except Exception as exc:
            self._store_result("failed", error=str(exc))
            self._send_json(LAST_RESULT, status=HTTPStatus.BAD_GATEWAY)
            return

        self._store_result(
            "passed",
            result={
                "audio_bytes": len(audio_bytes),
                "asr": asr_payload,
            },
        )
        self._send_json(LAST_RESULT)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _forward_to_asr(self, audio_bytes: bytes) -> dict[str, object]:
        url = _validate_http_url(f"{self.echobot_base_url.rstrip('/')}/api/web/asr")
        http_request = request.Request(
            url,
            data=audio_bytes,
            headers={"Content-Type": "audio/wav"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=45) as response:  # nosec B310  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
                payload = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"EchoBot ASR failed: status={exc.code}, detail={detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"EchoBot ASR network error: {exc.reason}") from exc
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise RuntimeError("EchoBot ASR returned a non-object response")
        return parsed

    def _store_result(
        self,
        status: str,
        *,
        result: dict[str, object] | None = None,
        error: str | None = None,
    ) -> None:
        LAST_RESULT.update(
            {
                "status": status,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "result": result,
                "error": error,
                "client": self.client_address[0],
            }
        )

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send_bytes(
            status,
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _validate_http_url(url: str) -> str:
    parsed = parse.urlparse(str(url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("smoke-test URL must be an absolute HTTP(S) URL")
    return parsed.geturl()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--echobot-base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    MicSmokeHandler.echobot_base_url = args.echobot_base_url
    server = ThreadingHTTPServer((args.host, args.port), MicSmokeHandler)
    print(f"mobile mic smoke server listening on http://{args.host}:{args.port}")
    print(f"forwarding ASR requests to {args.echobot_base_url}/api/web/asr")
    server.serve_forever()


if __name__ == "__main__":
    main()
