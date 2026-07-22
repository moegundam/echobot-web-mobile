from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from echobot.app.services.session_runtime_context import (
    _runtime_live2d_profile,
    _runtime_llm_profile,
)
from echobot.app.services.session_turn_runtime import _resolve_llm_profile


class _DeletedProfileService:
    def get_runtime_profile(self, profile_id: str) -> dict[str, object]:
        raise ValueError(f"Unknown profile: {profile_id}")


def _runtime_with_deleted_profile_service(service_name: str):
    return SimpleNamespace(
        model_profile_service=SimpleNamespace(
            get_profile_for_runtime=lambda profile_id: {
                "profile_id": profile_id,
                "source": "legacy",
            },
        ),
        **{service_name: _DeletedProfileService()},
    )


def test_deleted_llm_profile_does_not_fallback_to_legacy_profile() -> None:
    runtime = _runtime_with_deleted_profile_service("llm_model_service")

    result = asyncio.run(
        _runtime_llm_profile(runtime, "deleted-llm", {"source": "catalog"}),
    )

    assert result == {}


def test_deleted_live2d_profile_does_not_fallback_to_legacy_profile() -> None:
    runtime = _runtime_with_deleted_profile_service("live2d_model_service")

    result = asyncio.run(
        _runtime_live2d_profile(runtime, "deleted-live2d", {"source": "catalog"}),
    )

    assert result == {}


def test_turn_runtime_rejects_deleted_llm_profile_without_active_fallback() -> None:
    active_profile_calls: list[bool] = []
    runtime = SimpleNamespace(
        llm_model_service=SimpleNamespace(
            get_runtime_profile=lambda profile_id: (_ for _ in ()).throw(
                ValueError(f"Unknown profile: {profile_id}"),
            ),
            active_runtime_profile=lambda: active_profile_calls.append(True) or {},
        ),
        model_profile_service=None,
    )

    with pytest.raises(ValueError, match="Unknown profile: deleted-llm"):
        asyncio.run(_resolve_llm_profile(runtime, "deleted-llm"))

    assert active_profile_calls == []
