from __future__ import annotations

import asyncio
import shutil
import tarfile
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ...speech_assets import (
    acquire_download_lock,
    download_file,
    file_name_from_url,
    relative_to_root,
    replace_directory,
    safe_extract_tar,
    write_download_metadata,
)
from ..models import ProviderStatusSnapshot, TranscriptionResult
from ..sherpa import load_sherpa_module, sherpa_dependency_error_message
from .base import ASRProvider


DEFAULT_SENSE_VOICE_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09.tar.bz2"
)


@dataclass(slots=True)
class _StatusState:
    state: str
    detail: str


@dataclass(slots=True, frozen=True)
class SenseVoiceModelPaths:
    root_dir: Path
    model_file: Path
    tokens_file: Path


@dataclass(slots=True, frozen=True)
class SenseVoiceDownloadSettings:
    model_url: str
    timeout_seconds: float
    allow_private_download: bool


class SenseVoiceModelManager:
    def __init__(
        self,
        workspace: Path,
        *,
        model_root_dir: Path | None = None,
        model_url: str = DEFAULT_SENSE_VOICE_MODEL_URL,
        timeout_seconds: float = 600.0,
        allow_private_download: bool = False,
    ) -> None:
        root_dir = model_root_dir or (
            workspace / ".echobot" / "models" / "asr" / "sherpa-sense-voice"
        )
        self._paths = SenseVoiceModelPaths(
            root_dir=root_dir,
            model_file=root_dir / "model.int8.onnx",
            tokens_file=root_dir / "tokens.txt",
        )
        self._settings = SenseVoiceDownloadSettings(
            model_url=model_url,
            timeout_seconds=timeout_seconds,
            allow_private_download=allow_private_download,
        )

    @property
    def paths(self) -> SenseVoiceModelPaths:
        return self._paths

    def models_ready(self) -> bool:
        return not self.missing_files()

    def missing_files(self) -> list[Path]:
        required_files = [
            self._paths.model_file,
            self._paths.tokens_file,
        ]
        return [path for path in required_files if not path.is_file()]

    def prepare_required_files(self) -> SenseVoiceModelPaths:
        if self.models_ready():
            return self._paths

        self._paths.root_dir.parent.mkdir(parents=True, exist_ok=True)
        with self._acquire_download_lock():
            if self.models_ready():
                return self._paths
            self._install_model()
        return self._paths

    def _install_model(self) -> None:
        with tempfile.TemporaryDirectory(prefix="echobot_sense_voice_") as temp_dir:
            temp_root = Path(temp_dir)
            archive_name = file_name_from_url(
                self._settings.model_url,
                allow_private=self._settings.allow_private_download,
            )
            archive_path = temp_root / archive_name
            extract_dir = temp_root / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)

            download_file(
                self._settings.model_url,
                archive_path,
                timeout_seconds=self._settings.timeout_seconds,
                allow_private=self._settings.allow_private_download,
                progress_label="SenseVoice ASR model",
            )
            with tarfile.open(archive_path, "r:*") as archive:
                safe_extract_tar(archive, extract_dir)

            source_dir = self._find_directory_with_model_files(extract_dir)
            temp_install_dir = self._paths.root_dir.with_name(f"{self._paths.root_dir.name}.tmp")
            if temp_install_dir.exists():
                shutil.rmtree(temp_install_dir)
            temp_install_dir.mkdir(parents=True, exist_ok=True)

            shutil.copy2(source_dir / "model.int8.onnx", temp_install_dir / "model.int8.onnx")
            shutil.copy2(source_dir / "tokens.txt", temp_install_dir / "tokens.txt")
            write_download_metadata(
                temp_install_dir / "metadata.json",
                name="sherpa-sense-voice",
                source_url=self._settings.model_url,
            )
            replace_directory(temp_install_dir, self._paths.root_dir)

    @staticmethod
    def _find_directory_with_model_files(root: Path) -> Path:
        for directory in [root, *sorted(path for path in root.rglob("*") if path.is_dir())]:
            if not (directory / "model.int8.onnx").is_file():
                continue
            if not (directory / "tokens.txt").is_file():
                continue
            return directory
        raise FileNotFoundError("Unable to locate SenseVoice model files in extracted archive")

    @contextmanager
    def _acquire_download_lock(self):
        lock_path = self._paths.root_dir.parent / ".sense-voice.download.lock"
        with acquire_download_lock(
            lock_path,
            timeout_seconds=self._settings.timeout_seconds,
            timeout_message="Timed out while waiting for SenseVoice model download lock",
        ):
            yield


class SherpaSenseVoiceASRProvider(ASRProvider):
    name = "sherpa-sense-voice"
    label = "Sherpa SenseVoice"

    def __init__(
        self,
        workspace: Path,
        *,
        sample_rate: int = 16000,
        auto_download: bool = True,
        model_root_dir: Path | None = None,
        execution_provider: str = "cpu",
        num_threads: int = 2,
        language: str = "auto",
        use_itn: bool = False,
        model_url: str = DEFAULT_SENSE_VOICE_MODEL_URL,
        download_timeout_seconds: float = 600.0,
        allow_private_download: bool = False,
    ) -> None:
        self._sample_rate = sample_rate
        self._auto_download = auto_download
        self._execution_provider = execution_provider
        self._num_threads = max(1, num_threads)
        self._language = language
        self._use_itn = use_itn
        self._model_manager = SenseVoiceModelManager(
            workspace,
            model_root_dir=model_root_dir,
            model_url=model_url,
            timeout_seconds=download_timeout_seconds,
            allow_private_download=allow_private_download,
        )
        self._status_lock = asyncio.Lock()
        self._runtime_lock = threading.Lock()
        self._recognizer_lock = threading.Lock()
        self._prepare_task: asyncio.Task[None] | None = None
        self._recognizer = None
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
            kind="asr",
            name=self.name,
            label=self.label,
            selected=False,
            available=self._state.state == "ready",
            state=self._state.state,
            detail=self._state.detail,
            resource_directory=str(self._model_manager.paths.root_dir),
        )

    async def transcribe_samples(self, samples: list[float]) -> TranscriptionResult:
        if not samples:
            return TranscriptionResult(text="")

        await self._require_runtime_ready()
        return await asyncio.to_thread(self._transcribe_samples_sync, samples)

    async def _require_runtime_ready(self) -> None:
        await self._maybe_start_prepare()
        self._refresh_state_from_disk()
        if self._state.state != "ready":
            raise RuntimeError(self._state.detail)
        await asyncio.to_thread(self._ensure_runtime_loaded)

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
                name="echobot_sense_voice_prepare",
            )

    async def _prepare_model(self) -> None:
        self._set_state("downloading", "正在自动下载 SenseVoice 模型，请稍候。")
        try:
            await asyncio.to_thread(self._model_manager.prepare_required_files)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._set_state("error", f"SenseVoice 模型下载失败: {exc}")
            return

        self._reset_runtime_objects()
        self._refresh_state_from_disk()

    def _refresh_state_from_disk(self) -> None:
        if self._dependency_error is not None:
            self._set_state("unavailable", self._dependency_error)
            return

        missing_files = self._model_manager.missing_files()
        if not missing_files:
            self._set_state("ready", "SenseVoice 已就绪。")
            return

        if self._prepare_task is not None and not self._prepare_task.done():
            self._set_state("downloading", "正在自动下载 SenseVoice 模型，请稍候。")
            return

        relative_paths = ", ".join(
            relative_to_root(path, self._model_manager.paths.root_dir)
            for path in missing_files
        )
        if self._auto_download:
            self._set_state(
                "missing",
                f"SenseVoice 模型尚未准备，正在等待下载: {relative_paths}",
            )
        else:
            self._set_state(
                "missing",
                f"缺少 SenseVoice 模型文件: {relative_paths}",
            )

    def _set_state(self, state: str, detail: str) -> None:
        self._state = _StatusState(state=state, detail=detail)

    def _reset_runtime_objects(self) -> None:
        with self._runtime_lock:
            self._recognizer = None

    def _ensure_runtime_loaded(self) -> None:
        with self._runtime_lock:
            if self._recognizer is not None:
                return

            try:
                sherpa_onnx = load_sherpa_module()
                paths = self._model_manager.paths
                self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                    model=str(paths.model_file),
                    tokens=str(paths.tokens_file),
                    num_threads=self._num_threads,
                    sample_rate=self._sample_rate,
                    provider=self._execution_provider,
                    language=self._language,
                    use_itn=self._use_itn,
                )
            except Exception as exc:
                self._set_state("error", f"SenseVoice 初始化失败: {exc}")
                raise

    def _transcribe_samples_sync(self, samples: list[float]) -> TranscriptionResult:
        self._ensure_runtime_loaded()
        with self._recognizer_lock:
            stream = self._recognizer.create_stream()
            stream.accept_waveform(self._sample_rate, samples)
            self._recognizer.decode_stream(stream)
            result = stream.result

        text = str(getattr(result, "text", "") or "").strip()
        language = str(getattr(result, "lang", "") or "").strip()
        return TranscriptionResult(text=text, language=language)
