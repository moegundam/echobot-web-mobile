from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..auth import user_storage_key
from ...orchestration import role_name_from_metadata
from .runtime_context_cache import get_runtime_context_cache
from .stage_events import StageEventPublishRequest


logger = logging.getLogger(__name__)
RUNTIME_CONTEXT_EVENT_SCHEMA_VERSION = 1


async def notify_session_runtime_context_changed(
    runtime: Any,
    session_name: str,
    *,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    cache = get_runtime_context_cache(runtime)
    revision = await cache.invalidate(session_name)
    await _publish_change_event(
        runtime,
        session_name,
        revision,
        reason,
        metadata=metadata,
    )
    return revision


async def notify_sessions_runtime_context_changed(
    runtime: Any,
    session_names: list[str] | tuple[str, ...] | set[str],
    *,
    reason: str,
) -> dict[str, str]:
    """Invalidate and notify a deduplicated set of sessions."""
    revisions: dict[str, str] = {}
    for session_name in dict.fromkeys(str(item).strip() for item in session_names):
        if not session_name:
            continue
        revisions[session_name] = await notify_session_runtime_context_changed(
            runtime,
            session_name,
            reason=reason,
        )
    return revisions


async def notify_roles_runtime_context_changed(
    runtime: Any,
    role_names: set[str] | list[str] | tuple[str, ...],
    *,
    reason: str,
) -> dict[str, str]:
    """Notify only sessions whose effective role uses one of ``role_names``."""
    normalized_roles = {
        str(role_name).strip()
        for role_name in role_names
        if str(role_name).strip()
    }
    if not normalized_roles:
        return {}
    session_service = getattr(runtime, "session_service", None)
    if session_service is None:
        return {}

    try:
        sessions = await session_service.list_sessions()
    except Exception:
        logger.exception("Unable to list sessions for runtime-context invalidation")
        return {}

    override_service = getattr(runtime, "session_runtime_override_service", None)
    affected: list[str] = []
    for session in sessions:
        session_name = str(getattr(session, "name", "") or "").strip()
        if not session_name:
            continue
        effective_roles = {
            role_name_from_metadata(getattr(session, "metadata", {}) or {}),
        }
        if override_service is not None:
            try:
                override = await asyncio.to_thread(
                    override_service.get_override,
                    session_name,
                )
            except Exception:
                logger.exception(
                    "Unable to read session override for %s",
                    session_name,
                )
                override = {}
            override_role = str(
                override.get("role_name") if isinstance(override, dict) else "",
            ).strip()
            if override_role:
                effective_roles.add(override_role)
        if effective_roles & normalized_roles:
            affected.append(session_name)
    return await notify_sessions_runtime_context_changed(
        runtime,
        affected,
        reason=reason,
    )


async def notify_all_runtime_contexts_changed(
    runtime: Any,
    *,
    reason: str,
) -> dict[str, str]:
    cache = get_runtime_context_cache(runtime)
    await cache.invalidate_all()
    session_service = getattr(runtime, "session_service", None)
    if session_service is None:
        return {}

    try:
        sessions = await session_service.list_sessions()
    except Exception:
        logger.exception("Unable to list sessions for global runtime-context invalidation")
        return {}
    revisions: dict[str, str] = {}
    for session in sessions:
        session_name = str(getattr(session, "name", "") or "").strip()
        if not session_name:
            continue
        revision = await cache.current_revision(session_name)
        revisions[session_name] = revision
        await _publish_change_event(runtime, session_name, revision, reason)
    return revisions


async def notify_runtime_tree_contexts_changed(
    runtime: Any,
    *,
    reason: str,
) -> None:
    """Invalidate process and cached user runtimes after owner-global changes."""
    owner_runtime = getattr(runtime, "parent", None) or runtime
    targets = [owner_runtime]
    user_runtime_factory = getattr(owner_runtime, "user_runtime_factory", None)
    cached_runtimes = getattr(user_runtime_factory, "cached_runtimes", None)
    if callable(cached_runtimes):
        targets.extend(cached_runtimes())

    unique_targets = list({id(target): target for target in targets}.values())
    await asyncio.gather(
        *(
            notify_all_runtime_contexts_changed(target, reason=reason)
            for target in unique_targets
        ),
    )


async def _publish_change_event(
    runtime: Any,
    session_name: str,
    revision: str,
    reason: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    broker = getattr(runtime, "stage_event_broker", None)
    if broker is None:
        return
    try:
        event_metadata = dict(metadata or {})
        event_metadata.update(
            revision=revision,
            reason=str(reason or "runtime_updated").strip() or "runtime_updated",
            schema_version=RUNTIME_CONTEXT_EVENT_SCHEMA_VERSION,
        )
        await broker.publish(
            scope_key=_scope_key(runtime),
            request=StageEventPublishRequest(
                kind="runtime_context_changed",
                session_name=session_name,
                text="",
                source="runtime",
                metadata=event_metadata,
            ),
        )
    except Exception:
        logger.exception(
            "Unable to publish runtime context change for session %s",
            session_name,
        )


def _scope_key(runtime: Any) -> str:
    user_id = str(getattr(runtime, "user_id", "") or "").strip()
    return user_storage_key(user_id) if user_id else "default"
