from __future__ import annotations

from typing import Any


CHANNEL_TYPE_METADATA_KEY = "channel_type"
CHANNEL_INTEGRATION_METADATA_KEY = "channel_integration_id"


def channel_type_from_metadata(metadata: dict[str, Any] | None) -> str:
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get(CHANNEL_TYPE_METADATA_KEY) or "").strip().lower()


def channel_integration_id_from_metadata(metadata: dict[str, Any] | None) -> str:
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get(CHANNEL_INTEGRATION_METADATA_KEY) or "").strip().lower()


def set_channel_binding(
    metadata: dict[str, Any] | None,
    *,
    channel_type: str = "",
    channel_integration_id: str = "",
) -> dict[str, Any]:
    next_metadata = dict(metadata or {})
    normalized_type = str(channel_type or "").strip().lower()
    normalized_integration_id = str(channel_integration_id or "").strip().lower()
    if normalized_type:
        next_metadata[CHANNEL_TYPE_METADATA_KEY] = normalized_type
    else:
        next_metadata.pop(CHANNEL_TYPE_METADATA_KEY, None)
    if normalized_integration_id:
        next_metadata[CHANNEL_INTEGRATION_METADATA_KEY] = normalized_integration_id
    else:
        next_metadata.pop(CHANNEL_INTEGRATION_METADATA_KEY, None)
    return next_metadata
