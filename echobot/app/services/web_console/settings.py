from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ....runtime.settings import RuntimeSettings, RuntimeSettingsStore


class WebRuntimeSettingsService:
    def __init__(self, workspace: Path, storage_root: Path | None = None) -> None:
        root = storage_root or workspace / ".echobot"
        self._store = RuntimeSettingsStore(
            root / "runtime_settings.json",
        )

    async def load_settings(self) -> RuntimeSettings:
        return await asyncio.to_thread(self._store.load)

    async def save_selected_asr_provider(
        self,
        provider_name: str,
    ) -> dict[str, Any]:
        settings = await asyncio.to_thread(
            self._store.update_named_value,
            "selected_asr_provider",
            provider_name,
        )
        return settings.to_dict()


__all__ = [
    "WebRuntimeSettingsService",
]
