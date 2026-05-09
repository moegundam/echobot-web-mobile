from __future__ import annotations

from typing import Any

from .runtime_model_repositories import LLMModelRepository
from .session_catalog import llm_model_from_profile, project_llm_models


class LLMModelService:
    """LLM model use cases and API projection."""

    def __init__(self, repository: LLMModelRepository) -> None:
        self._repository = repository

    def list_models(self) -> dict[str, Any]:
        payload = self._repository.list_payload()
        return {
            "active_model_id": str(payload.get("active_profile_id") or "a"),
            "models": [
                model.model_dump(mode="json")
                for model in project_llm_models(payload)
            ],
        }

    def legacy_payload(self) -> dict[str, Any]:
        return self._repository.list_payload()

    def create_model(
        self,
        *,
        name: str,
        source_model_id: str | None = None,
    ) -> dict[str, Any]:
        profile = self._repository.create(
            name=name,
            source_model_id=source_model_id,
        )
        return llm_model_from_profile(profile).model_dump(mode="json")

    def update_model(self, model_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        profile = self._repository.update(model_id, updates)
        return llm_model_from_profile(profile).model_dump(mode="json")

    def activate_model(self, model_id: str) -> dict[str, Any]:
        self._repository.activate(model_id)
        return self.list_models()

    def delete_model(self, model_id: str) -> dict[str, Any]:
        self._repository.delete(model_id)
        return self.list_models()

    def get_runtime_profile(self, model_id: str) -> dict[str, Any]:
        return self._repository.get_runtime_profile(model_id)

    def active_runtime_profile(self) -> dict[str, Any]:
        return self._repository.active_runtime_profile()
