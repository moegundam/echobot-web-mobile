from __future__ import annotations

from typing import Any


CHANNEL_TYPE_METADATA_KEY = "channel_type"
CHANNEL_INTEGRATION_METADATA_KEY = "channel_integration_id"


class ChannelBindingConflictError(ValueError):
    """Raised when one channel integration would resolve to multiple Sessions."""


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


def matches_channel_binding(
    metadata: dict[str, Any] | None,
    *,
    channel_type: str,
    channel_integration_id: str = "",
) -> bool:
    normalized_channel_type = str(channel_type or "").strip().lower()
    normalized_integration_id = str(channel_integration_id or "").strip().lower()
    if not normalized_channel_type and not normalized_integration_id:
        return False

    bound_type = channel_type_from_metadata(metadata)
    bound_integration_id = channel_integration_id_from_metadata(metadata)
    if bound_integration_id:
        return bound_integration_id in {
            normalized_integration_id,
            normalized_channel_type,
        }
    if bound_type:
        return bound_type == normalized_channel_type
    return False


def channel_bindings_overlap(
    metadata: dict[str, Any] | None,
    *,
    channel_type: str,
    channel_integration_id: str = "",
) -> bool:
    """Return whether two bindings can match the same inbound channel route."""
    candidate_metadata = set_channel_binding(
        {},
        channel_type=channel_type,
        channel_integration_id=channel_integration_id,
    )
    if not candidate_metadata:
        return False
    return matches_channel_binding(
        metadata,
        channel_type=channel_type,
        channel_integration_id=channel_integration_id,
    ) or matches_channel_binding(
        candidate_metadata,
        channel_type=channel_type_from_metadata(metadata),
        channel_integration_id=channel_integration_id_from_metadata(metadata),
    )
