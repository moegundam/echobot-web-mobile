from __future__ import annotations

from typing import Any

from .runtime_model_repositories import Live2DModelRepository
from .session_catalog import live2d_model_from_profile, project_live2d_models


class Live2DModelService:
    """Live2D model use cases and API projection."""

    def __init__(self, repository: Live2DModelRepository) -> None:
        self._repository = repository

    def list_models(self, catalog: list[dict[str, Any]]) -> dict[str, Any]:
        payload = self._repository.list_payload()
        return {
            "active_live2d_model_id": str(payload.get("active_profile_id") or "a"),
            "models": [
                model.model_dump(mode="json")
                for model in project_live2d_models(payload, catalog)
            ],
            "catalog": catalog,
        }

    def legacy_payload(self) -> dict[str, Any]:
        return self._repository.list_payload()

    def create_model(
        self,
        *,
        name: str,
        source_model_id: str | None = None,
        catalog: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        profile = self._repository.create(
            name=name,
            source_model_id=source_model_id,
        )
        return self._project(profile, catalog or [])

    def update_model(
        self,
        model_id: str,
        updates: dict[str, Any],
        *,
        catalog: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        profile = self._repository.update(model_id, updates)
        return self._project(profile, catalog or [])

    def activate_model(self, model_id: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
        self._repository.activate(model_id)
        return self.list_models(catalog)

    def delete_model(self, model_id: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
        self._repository.delete(model_id)
        return self.list_models(catalog)

    def get_runtime_profile(self, model_id: str) -> dict[str, Any]:
        return self._repository.get_runtime_profile(model_id)

    def active_runtime_profile(self) -> dict[str, Any]:
        return self._repository.active_runtime_profile()

    @staticmethod
    def _project(profile: dict[str, Any], catalog: list[dict[str, Any]]) -> dict[str, Any]:
        catalog_by_key = {
            str(item.get("selection_key") or ""): item
            for item in catalog
            if isinstance(item, dict)
        }
        return live2d_model_from_profile(profile, catalog_by_key).model_dump(mode="json")
