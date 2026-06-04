from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path

from ...base import (
    SynthesizedSpeech,
    TTSProvider,
    TTSProviderStatus,
    TTSSynthesisOptions,
    VoiceOption,
)
from .model_manager import (
    DEFAULT_KOKORO_URL,
    KokoroModelManager,
    KokoroPreparationCancelled,
)
from .runtime import KokoroRuntime, kokoro_dependency_error_message
from .voices import (
    KOKORO_SPEAKER_NAMES,
    kokoro_voice_options,
    normalize_kokoro_voice_name,
    speaker_id_for_voice,
)


@dataclass(slots=True)
class _StatusState:
    state: str
    detail: str


class KokoroTTSProvider(TTSProvider):
    name = "kokoro"
    label = "Sherpa Kokoro"

    def __init__(
        self,
        workspace: Path,
        *,
        auto_download: bool = True,
        model_root_dir: Path | None = None,
        provider: str = "cpu",
        num_threads: int = 2,
        default_voice: str = "zf_001",
        model_url: str = DEFAULT_KOKORO_URL,
        download_timeout_seconds: float = 600.0,
        allow_private_download: bool = False,
        length_scale: float = 1.0,
        lang: str = "",
    ) -> None:
        self._default_voice = normalize_kokoro_voice_name(default_voice)
        self._auto_download = auto_download
        self._length_scale = max(0.1, length_scale)
        self._model_manager = KokoroModelManager(
            workspace,
            model_root_dir=model_root_dir,
            model_url=model_url,
            timeout_seconds=download_timeout_seconds,
            allow_private_download=allow_private_download,
        )
        self._status_lock = asyncio.Lock()
        self._prepare_task: asyncio.Task[None] | None = None
        self._prepare_stop_event: threading.Event | None = None
        self._runtime = KokoroRuntime(
            provider=provider,
            num_threads=max(1, num_threads),
            length_scale=self._length_scale,
            lang=lang,
        )
        self._dependency_error = kokoro_dependency_error_message()
        self._last_prepare_error = ""

    @property
    def default_voice(self) -> str:
        return self._default_voice

    def status(self) -> TTSProviderStatus:
        state = self._status_state()
        return TTSProviderStatus(
            name=self.name,
            label=self.label,
            available=state.state == "ready",
            state=state.state,
            detail=state.detail,
        )

    async def list_voices(self) -> list[VoiceOption]:
        return kokoro_voice_options()

    async def synthesize(
        self,
        *,
        text: str,
        options: TTSSynthesisOptions | None = None,
    ) -> SynthesizedSpeech:
        synthesis_options = options or TTSSynthesisOptions()
        await self._ensure_ready_for_synthesis()

        selected_voice = (synthesis_options.voice or self._default_voice).strip()
        speaker_id = speaker_id_for_voice(selected_voice)
        speed = synthesis_options.speed or 1.0
        audio_bytes = await asyncio.to_thread(
            self._synthesize_sync,
            text,
            speaker_id,
            speed,
        )
        return SynthesizedSpeech(
            audio_bytes=audio_bytes,
            content_type="audio/wav",
            file_extension="wav",
            provider=self.name,
            voice=KOKORO_SPEAKER_NAMES[speaker_id],
        )

    async def close(self) -> None:
        if self._prepare_stop_event is not None:
            self._prepare_stop_event.set()
        task = self._prepare_task
        if task is None or task.done():
            return
        await asyncio.gather(task, return_exceptions=True)

    async def _ensure_ready_for_synthesis(self) -> None:
        await self._ensure_models_ready()
        await asyncio.to_thread(self._ensure_runtime_loaded)

    async def _ensure_models_ready(self) -> None:
        state = self._status_state()
        if state.state == "ready":
            return
        if state.state == "unavailable":
            raise RuntimeError(state.detail)
        if not self._auto_download:
            raise RuntimeError(state.detail)

        await self._prepare_models()
        state = self._status_state()
        if state.state != "ready":
            raise RuntimeError(state.detail)

    async def _prepare_models(self) -> None:
        async with self._status_lock:
            state = self._status_state()
            if state.state == "ready":
                return
            if state.state == "unavailable":
                raise RuntimeError(state.detail)
            if not self._auto_download:
                raise RuntimeError(state.detail)

            if self._prepare_task is None or self._prepare_task.done():
                self._last_prepare_error = ""
                self._prepare_stop_event = threading.Event()
                self._prepare_task = asyncio.create_task(
                    self._prepare_model(self._prepare_stop_event),
                    name="echobot_kokoro_tts_model_prepare",
                )

            task = self._prepare_task

        await task

    async def _prepare_model(self, stop_event: threading.Event) -> None:
        try:
            await asyncio.to_thread(
                self._model_manager.prepare_required_files,
                stop_event=stop_event,
            )
        except KokoroPreparationCancelled:
            return
        except Exception as exc:
            self._last_prepare_error = f"Kokoro 语音模型准备失败: {exc}"
            return

        self._last_prepare_error = ""
        self._reset_runtime_objects()

    def _status_state(self) -> _StatusState:
        if self._dependency_error is not None:
            return _StatusState(state="unavailable", detail=self._dependency_error)

        if self._prepare_task is not None and not self._prepare_task.done():
            return _StatusState(
                state="downloading",
                detail="正在准备 Kokoro 语音模型，请稍候。",
            )

        if self._last_prepare_error:
            return _StatusState(
                state="error",
                detail=self._last_prepare_error,
            )

        missing_files = self._model_manager.missing_files()
        if not missing_files:
            return _StatusState(
                state="ready",
                detail="Kokoro TTS 已就绪。",
            )

        relative_paths = ", ".join(
            _relative_to_root(path, self._model_manager.paths.root_dir)
            for path in missing_files
        )
        if self._auto_download:
            return _StatusState(
                "missing",
                f"Kokoro 语音模型尚未准备，首次合成时会自动下载: {relative_paths}",
            )
        return _StatusState(
            "missing",
            f"缺少 Kokoro 语音模型文件: {relative_paths}",
        )

    def _reset_runtime_objects(self) -> None:
        self._runtime.reset()

    def _ensure_runtime_loaded(self) -> None:
        try:
            self._runtime.ensure_loaded(
                self._model_manager.paths,
                self._model_manager.lexicon_files(),
            )
        except Exception as exc:
            self._last_prepare_error = f"Kokoro TTS 初始化失败: {exc}"
            raise

    def _synthesize_sync(self, text: str, speaker_id: int, speed: float) -> bytes:
        self._ensure_runtime_loaded()
        return self._runtime.synthesize(
            text=text,
            speaker_id=speaker_id,
            speed=speed,
        )


def _relative_to_root(path: Path, root_dir: Path) -> str:
    try:
        return path.relative_to(root_dir).as_posix()
    except ValueError:
        return path.name
