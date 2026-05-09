from __future__ import annotations

from typing import Any

from .runtime_model_repositories import VoiceModelRepository
from .session_catalog import project_voice_profiles, voice_profile_from_profile


class VoiceModelService:
    """Voice-profile use cases and API projection."""

    def __init__(self, repository: VoiceModelRepository) -> None:
        self._repository = repository

    def list_profiles(self) -> dict[str, Any]:
        payload = self._repository.list_payload()
        return {
            "active_voice_profile_id": str(payload.get("active_profile_id") or "a"),
            "profiles": [
                profile.model_dump(mode="json")
                for profile in project_voice_profiles(payload)
            ],
        }

    def legacy_payload(self) -> dict[str, Any]:
        return self._repository.list_payload()

    def create_profile(
        self,
        *,
        name: str,
        source_profile_id: str | None = None,
    ) -> dict[str, Any]:
        profile = self._repository.create(
            name=name,
            source_profile_id=source_profile_id,
        )
        return voice_profile_from_profile(profile).model_dump(mode="json")

    def update_profile(self, profile_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        profile = self._repository.update(profile_id, updates)
        return voice_profile_from_profile(profile).model_dump(mode="json")

    def activate_profile(self, profile_id: str) -> dict[str, Any]:
        self._repository.activate(profile_id)
        return self.list_profiles()

    def delete_profile(self, profile_id: str) -> dict[str, Any]:
        self._repository.delete(profile_id)
        return self.list_profiles()

    def get_runtime_profile(self, profile_id: str) -> dict[str, Any]:
        return self._repository.get_runtime_profile(profile_id)

    def active_runtime_profile(self) -> dict[str, Any]:
        return self._repository.active_runtime_profile()
