from __future__ import annotations

import asyncio

from .audio import read_wav_bytes
from .models import ASRStatusSnapshot, ProviderStatusSnapshot, TranscriptionResult
from .providers import ASRProvider
from .realtime import RealtimeASRSession
from .vad import VADProvider


class ASRService:
    def __init__(
        self,
        asr_providers: dict[str, ASRProvider],
        vad_providers: dict[str, VADProvider],
        *,
        selected_asr_provider: str,
        selected_vad_provider: str | None,
        sample_rate: int = 16000,
    ) -> None:
        if not asr_providers:
            raise ValueError("At least one ASR provider is required")
        if selected_asr_provider not in asr_providers:
            raise ValueError(f"Unknown ASR provider: {selected_asr_provider}")
        if selected_vad_provider is not None and selected_vad_provider not in vad_providers:
            raise ValueError(f"Unknown VAD provider: {selected_vad_provider}")
        if sample_rate <= 0:
            raise ValueError("ASR sample_rate must be positive")

        self._asr_providers = dict(asr_providers)
        self._vad_providers = dict(vad_providers)
        self._selected_asr_provider = selected_asr_provider
        self._selected_vad_provider = selected_vad_provider
        self._sample_rate = sample_rate

    @property
    def selected_asr_provider(self) -> str:
        return self._selected_asr_provider

    async def replace_asr_provider(
        self,
        provider_name: str,
        provider: ASRProvider,
        *,
        select: bool = False,
    ) -> None:
        normalized_name = provider_name.strip()
        if not normalized_name:
            raise ValueError("ASR provider name must not be empty")

        previous_provider = self._asr_providers.get(normalized_name)
        self._asr_providers[normalized_name] = provider
        if select:
            self._selected_asr_provider = normalized_name
            await self.on_startup()
        if previous_provider is not None and previous_provider is not provider:
            await previous_provider.close()

    def asr_provider_names(self) -> list[str]:
        return sorted(self._asr_providers)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    async def on_startup(self) -> None:
        startup_tasks = [self._active_asr_provider().on_startup()]
        active_vad_provider = self._active_vad_provider()
        if active_vad_provider is not None:
            startup_tasks.append(active_vad_provider.on_startup())
        await asyncio.gather(*startup_tasks)

    async def set_selected_asr_provider(self, provider_name: str) -> None:
        normalized_name = provider_name.strip()
        if not normalized_name:
            raise ValueError("ASR 语音识别模型名称不能为空")
        if normalized_name not in self._asr_providers:
            raise ValueError(f"未知的 ASR 语音识别模型：{normalized_name}")

        self._selected_asr_provider = normalized_name
        await self.on_startup()

    async def close(self) -> None:
        providers = [
            *self._asr_providers.values(),
            *self._vad_providers.values(),
        ]
        await asyncio.gather(
            *(provider.close() for provider in providers),
            return_exceptions=True,
        )

    async def status_snapshot(self) -> ASRStatusSnapshot:
        selected_asr_provider = self._selected_asr_provider
        selected_vad_provider = self._selected_vad_provider
        asr_statuses = await asyncio.gather(
            *(
                self._provider_status(
                    provider,
                    selected=name == selected_asr_provider,
                )
                for name, provider in sorted(self._asr_providers.items())
            )
        )
        vad_statuses = await asyncio.gather(
            *(
                self._provider_status(
                    provider,
                    selected=name == selected_vad_provider,
                )
                for name, provider in sorted(self._vad_providers.items())
            )
        )

        active_asr_status = self._selected_status(
            asr_statuses,
            selected_name=selected_asr_provider,
        )
        active_vad_status = self._selected_status(
            vad_statuses,
            selected_name=selected_vad_provider,
        )
        if active_asr_status is None:
            raise RuntimeError("Active ASR provider status is missing")

        return ASRStatusSnapshot(
            available=active_asr_status.available,
            state=active_asr_status.state,
            detail=self._build_service_detail(active_asr_status, active_vad_status),
            sample_rate=self._sample_rate,
            selected_asr_provider=selected_asr_provider,
            selected_vad_provider=selected_vad_provider or "",
            always_listen_supported=bool(active_vad_status and active_vad_status.available),
            asr_providers=asr_statuses,
            vad_providers=vad_statuses,
        )

    async def transcribe_wav_bytes(self, audio_bytes: bytes) -> TranscriptionResult:
        asr_provider = self._active_asr_provider()
        asr_status = await self._selected_provider_status(
            asr_provider,
            kind="asr",
            selected=True,
        )
        if not asr_status.available:
            raise RuntimeError(asr_status.detail)

        samples = await asyncio.to_thread(read_wav_bytes, audio_bytes, self._sample_rate)
        return await asr_provider.transcribe_samples(samples)

    async def create_realtime_session(self) -> RealtimeASRSession:
        asr_provider = self._active_asr_provider()
        asr_status = await self._selected_provider_status(
            asr_provider,
            kind="asr",
            selected=True,
        )
        if not asr_status.available:
            raise RuntimeError(asr_status.detail)

        active_vad_provider = self._active_vad_provider()
        if active_vad_provider is None:
            raise RuntimeError("当前未配置 VAD provider，无法启用常开麦。")

        vad_status = await self._selected_provider_status(
            active_vad_provider,
            kind="vad",
            selected=True,
        )
        if not vad_status.available:
            raise RuntimeError(vad_status.detail)

        vad_session = await active_vad_provider.create_session()
        return RealtimeASRSession(
            asr_provider,
            vad_session,
        )

    async def _active_provider_status(self) -> ProviderStatusSnapshot:
        return await self._selected_provider_status(
            self._active_asr_provider(),
            kind="asr",
            selected=True,
        )

    async def _provider_status(
        self,
        provider: ASRProvider | VADProvider,
        *,
        selected: bool,
    ) -> ProviderStatusSnapshot:
        snapshot = await provider.status_snapshot()
        return ProviderStatusSnapshot(
            kind=snapshot.kind,
            name=snapshot.name,
            label=snapshot.label,
            selected=selected,
            available=snapshot.available,
            state=snapshot.state,
            detail=snapshot.detail,
            resource_directory=snapshot.resource_directory,
        )

    async def _selected_provider_status(
        self,
        provider: ASRProvider | VADProvider,
        *,
        kind: str,
        selected: bool,
    ) -> ProviderStatusSnapshot:
        snapshot = await provider.status_snapshot()
        if snapshot.kind != kind:
            raise RuntimeError(f"Unexpected provider kind: {snapshot.kind}")
        return ProviderStatusSnapshot(
            kind=snapshot.kind,
            name=snapshot.name,
            label=snapshot.label,
            selected=selected,
            available=snapshot.available,
            state=snapshot.state,
            detail=snapshot.detail,
            resource_directory=snapshot.resource_directory,
        )

    def _active_asr_provider(self) -> ASRProvider:
        return self._asr_providers[self._selected_asr_provider]

    def _active_vad_provider(self) -> VADProvider | None:
        if self._selected_vad_provider is None:
            return None
        return self._vad_providers[self._selected_vad_provider]

    @staticmethod
    def _selected_status(
        statuses: list[ProviderStatusSnapshot],
        *,
        selected_name: str | None,
    ) -> ProviderStatusSnapshot | None:
        if selected_name is None:
            return None
        for status in statuses:
            if status.name == selected_name:
                return status
        return None

    @staticmethod
    def _build_service_detail(
        active_asr_status: ProviderStatusSnapshot,
        active_vad_status: ProviderStatusSnapshot | None,
    ) -> str:
        if not active_asr_status.available:
            return active_asr_status.detail

        base_detail = active_asr_status.detail or "语音识别已就绪。"
        if active_vad_status is None:
            return f"{base_detail} 常开麦已禁用：未配置 VAD provider。"
        if not active_vad_status.available:
            return f"{base_detail} 常开麦暂不可用：{active_vad_status.detail}"
        return base_detail
