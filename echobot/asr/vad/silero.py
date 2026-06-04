from __future__ import annotations

import asyncio
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ...speech_assets import (
    acquire_download_lock,
    download_file,
    relative_to_root,
    replace_directory,
    write_download_metadata,
)
from ..audio import pcm16le_bytes_to_floats
from ..models import ProviderStatusSnapshot
from ..sherpa import load_sherpa_module, sherpa_dependency_error_message
from .base import SpeechSegment, VADProvider, VADSession, VADStepResult


DEFAULT_SILERO_VAD_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "silero_vad.onnx"
)


@dataclass(slots=True)
class _StatusState:
    state: str
    detail: str


@dataclass(slots=True, frozen=True)
class SileroModelPaths:
    root_dir: Path
    model_file: Path


@dataclass(slots=True, frozen=True)
class SileroDownloadSettings:
    model_url: str
    timeout_seconds: float
    allow_private_download: bool


class SileroModelManager:
    def __init__(
        self,
        workspace: Path,
        *,
        model_root_dir: Path | None = None,
        model_url: str = DEFAULT_SILERO_VAD_MODEL_URL,
        timeout_seconds: float = 600.0,
        allow_private_download: bool = False,
    ) -> None:
        root_dir = model_root_dir or (
            workspace / ".echobot" / "models" / "vad" / "silero"
        )
        self._paths = SileroModelPaths(
            root_dir=root_dir,
            model_file=root_dir / "silero_vad.onnx",
        )
        self._settings = SileroDownloadSettings(
            model_url=model_url,
            timeout_seconds=timeout_seconds,
            allow_private_download=allow_private_download,
        )

    @property
    def paths(self) -> SileroModelPaths:
        return self._paths

    def models_ready(self) -> bool:
        return self._paths.model_file.is_file()

    def missing_files(self) -> list[Path]:
        if self.models_ready():
            return []
        return [self._paths.model_file]

    def prepare_required_files(self) -> SileroModelPaths:
        if self.models_ready():
            return self._paths

        self._paths.root_dir.parent.mkdir(parents=True, exist_ok=True)
        with self._acquire_download_lock():
            if self.models_ready():
                return self._paths
            self._install_model()
        return self._paths

    def _install_model(self) -> None:
        with tempfile.TemporaryDirectory(prefix="echobot_silero_vad_") as _temp_dir:
            temp_install_dir = self._paths.root_dir.with_name(f"{self._paths.root_dir.name}.tmp")
            if temp_install_dir.exists():
                shutil.rmtree(temp_install_dir)
            temp_install_dir.mkdir(parents=True, exist_ok=True)

            target_path = temp_install_dir / "silero_vad.onnx"
            download_file(
                self._settings.model_url,
                target_path,
                timeout_seconds=self._settings.timeout_seconds,
                allow_private=self._settings.allow_private_download,
                progress_label="Silero VAD model",
            )
            write_download_metadata(
                temp_install_dir / "metadata.json",
                name="silero-vad",
                source_url=self._settings.model_url,
            )
            replace_directory(temp_install_dir, self._paths.root_dir)

    @contextmanager
    def _acquire_download_lock(self):
        lock_path = self._paths.root_dir.parent / ".silero-vad.download.lock"
        with acquire_download_lock(
            lock_path,
            timeout_seconds=self._settings.timeout_seconds,
            timeout_message="Timed out while waiting for Silero VAD model download lock",
        ):
            yield


class SileroVADSession(VADSession):
    def __init__(self, detector, *, sample_rate: int) -> None:
        self._detector = detector
        self._sample_rate = sample_rate

    def accept_audio_bytes(self, audio_bytes: bytes) -> VADStepResult:
        samples = pcm16le_bytes_to_floats(audio_bytes)
        if not samples:
            return VADStepResult()

        was_speech_detected = bool(self._detector.is_speech_detected())
        self._detector.accept_waveform(samples)
        is_speech_detected = bool(self._detector.is_speech_detected())
        segments = self._consume_segments()

        return VADStepResult(
            speech_started=not was_speech_detected and is_speech_detected,
            speech_ended=was_speech_detected and not is_speech_detected and bool(segments),
            segments=segments,
        )

    def flush(self) -> VADStepResult:
        was_speech_detected = bool(self._detector.is_speech_detected())
        self._detector.flush()
        segments = self._consume_segments()
        return VADStepResult(
            speech_ended=was_speech_detected and bool(segments),
            segments=segments,
        )

    def reset(self) -> None:
        self._detector.reset()

    def _consume_segments(self) -> list[SpeechSegment]:
        segments: list[SpeechSegment] = []
        while not self._detector.empty():
            segment = self._detector.front
            segment_samples = list(segment.samples)
            segment_start_ms = round((float(segment.start) / self._sample_rate) * 1000)
            self._detector.pop()
            segments.append(
                SpeechSegment(
                    samples=segment_samples,
                    start_ms=segment_start_ms,
                )
            )
        return segments


class SileroVADProvider(VADProvider):
    name = "silero"
    label = "Silero VAD"

    def __init__(
        self,
        workspace: Path,
        *,
        sample_rate: int = 16000,
        auto_download: bool = True,
        model_root_dir: Path | None = None,
        execution_provider: str = "cpu",
        model_url: str = DEFAULT_SILERO_VAD_MODEL_URL,
        download_timeout_seconds: float = 600.0,
        allow_private_download: bool = False,
        threshold: float = 0.5,
        min_silence_duration: float = 0.4,
        min_speech_duration: float = 0.2,
        max_speech_duration: float = 30.0,
        window_size: int = 512,
    ) -> None:
        self._sample_rate = sample_rate
        self._auto_download = auto_download
        self._execution_provider = execution_provider
        self._threshold = threshold
        self._min_silence_duration = min_silence_duration
        self._min_speech_duration = min_speech_duration
        self._max_speech_duration = max_speech_duration
        self._window_size = window_size
        self._model_manager = SileroModelManager(
            workspace,
            model_root_dir=model_root_dir,
            model_url=model_url,
            timeout_seconds=download_timeout_seconds,
            allow_private_download=allow_private_download,
        )
        self._status_lock = asyncio.Lock()
        self._prepare_task: asyncio.Task[None] | None = None
        self._state = _StatusState(state="missing", detail="")
        self._dependency_error = sherpa_dependency_error_message()
        self._refresh_state_from_disk()

    async def on_startup(self) -> None:
        await self._maybe_start_prepare()

    async def close(self) -> None:
        task = self._prepare_task
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def status_snapshot(self) -> ProviderStatusSnapshot:
        self._refresh_state_from_disk()
        return ProviderStatusSnapshot(
            kind="vad",
            name=self.name,
            label=self.label,
            selected=False,
            available=self._state.state == "ready",
            state=self._state.state,
            detail=self._state.detail,
            resource_directory=str(self._model_manager.paths.root_dir),
        )

    async def create_session(self) -> VADSession:
        await self._require_runtime_ready()
        return await asyncio.to_thread(self._create_session_sync)

    async def _require_runtime_ready(self) -> None:
        await self._maybe_start_prepare()
        self._refresh_state_from_disk()
        if self._state.state != "ready":
            raise RuntimeError(self._state.detail)

    async def _maybe_start_prepare(self) -> None:
        async with self._status_lock:
            self._refresh_state_from_disk()
            if self._dependency_error is not None:
                return
            if self._state.state == "ready":
                return
            if not self._auto_download:
                return
            if self._prepare_task is not None and not self._prepare_task.done():
                return

            self._prepare_task = asyncio.create_task(
                self._prepare_model(),
                name="echobot_silero_vad_prepare",
            )

    async def _prepare_model(self) -> None:
        self._set_state("downloading", "正在自动下载 Silero VAD 模型，请稍候。")
        try:
            await asyncio.to_thread(self._model_manager.prepare_required_files)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._set_state("error", f"Silero VAD 模型下载失败: {exc}")
            return

        self._refresh_state_from_disk()

    def _refresh_state_from_disk(self) -> None:
        if self._dependency_error is not None:
            self._set_state("unavailable", self._dependency_error)
            return

        missing_files = self._model_manager.missing_files()
        if not missing_files:
            self._set_state("ready", "Silero VAD 已就绪。")
            return

        if self._prepare_task is not None and not self._prepare_task.done():
            self._set_state("downloading", "正在自动下载 Silero VAD 模型，请稍候。")
            return

        relative_paths = ", ".join(
            relative_to_root(path, self._model_manager.paths.root_dir)
            for path in missing_files
        )
        if self._auto_download:
            self._set_state(
                "missing",
                f"Silero VAD 模型尚未准备，正在等待下载: {relative_paths}",
            )
        else:
            self._set_state(
                "missing",
                f"缺少 Silero VAD 模型文件: {relative_paths}",
            )

    def _set_state(self, state: str, detail: str) -> None:
        self._state = _StatusState(state=state, detail=detail)

    def _create_session_sync(self) -> VADSession:
        sherpa_onnx = load_sherpa_module()
        detector = sherpa_onnx.VoiceActivityDetector(
            sherpa_onnx.VadModelConfig(
                silero_vad=sherpa_onnx.SileroVadModelConfig(
                    model=str(self._model_manager.paths.model_file),
                    threshold=self._threshold,
                    min_silence_duration=self._min_silence_duration,
                    min_speech_duration=self._min_speech_duration,
                    window_size=self._window_size,
                    max_speech_duration=self._max_speech_duration,
                ),
                sample_rate=self._sample_rate,
                num_threads=1,
                provider=self._execution_provider,
                debug=False,
            ),
            60,
        )
        return SileroVADSession(detector, sample_rate=self._sample_rate)
