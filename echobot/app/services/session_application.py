from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass

from ...orchestration import role_name_from_metadata, set_role_name, set_route_mode
from ..session_metadata import (
    ChannelBindingConflictError,
    channel_bindings_overlap,
    channel_integration_id_from_metadata,
    channel_type_from_metadata,
    set_channel_binding,
)
from .runtime_profile_composer import (
    apply_runtime_profile_for_role,
    runtime_bindings_for_role,
)
from .runtime_context_events import notify_session_runtime_context_changed


@dataclass(frozen=True)
class _RuntimeMutationSnapshot:
    current_session_name: str
    current_session_revision: int
    active_profile_id: str
    applied_model_profile: dict[str, object]
    model_profile_revision: int


class SessionApplicationService:
    """Coordinate Session-centered operations across chat, runtime, and channels."""

    def __init__(self, runtime) -> None:
        self._runtime = runtime

    async def list_sessions(self):
        return await self._runtime.session_service.list_sessions()

    async def current_session(self):
        return await self._runtime.session_service.load_current_session()

    async def switch_session(self, session_name: str):
        return await self._runtime.session_service.switch_session(session_name)

    async def create_session(
        self,
        *,
        name: str | None = None,
        role_name: str | None = None,
        route_mode=None,
        channel_type: str | None = None,
        channel_integration_id: str | None = None,
    ):
        normalized_role_name = self._require_role(role_name) if role_name else None
        next_channel_type = channel_type or ""
        next_channel_integration_id = channel_integration_id or ""
        if not next_channel_type and not next_channel_integration_id and normalized_role_name:
            (
                next_channel_type,
                next_channel_integration_id,
            ) = await self._default_channel_binding_for_role(normalized_role_name)
        async with self._runtime.session_binding_lock:
            if next_channel_type or next_channel_integration_id:
                await self._assert_channel_binding_available(
                    channel_type=next_channel_type,
                    channel_integration_id=next_channel_integration_id,
                )
            return await self._create_session_unlocked(
                name=name,
                role_name=normalized_role_name,
                route_mode=route_mode,
                channel_type=next_channel_type,
                channel_integration_id=next_channel_integration_id,
            )

    async def _create_session_unlocked(
        self,
        *,
        name: str | None,
        role_name: str | None,
        route_mode,
        channel_type: str,
        channel_integration_id: str,
    ):
        if name:
            session_lock = await self._runtime.session_service.session_lock(name)
            async with session_lock:
                return await self._create_session_transaction(
                    name=name,
                    role_name=role_name,
                    route_mode=route_mode,
                    channel_type=channel_type,
                    channel_integration_id=channel_integration_id,
                )
        return await self._create_session_transaction(
            name=name,
            role_name=role_name,
            route_mode=route_mode,
            channel_type=channel_type,
            channel_integration_id=channel_integration_id,
        )

    async def _create_session_transaction(
        self,
        *,
        name: str | None,
        role_name: str | None,
        route_mode,
        channel_type: str,
        channel_integration_id: str,
    ):
        snapshot = await self._capture_runtime_snapshot()
        session = None
        expected_current_pointer: tuple[str, int] | None = None
        expected_model_profile_revision = snapshot.model_profile_revision
        try:
            session = await self._runtime.session_service.create_session(name)
            expected_current_pointer = await self._current_session_pointer(session.name)
            if role_name:
                session = await self._runtime.chat_service.set_role(
                    session.name,
                    role_name,
                )
                expected_current_pointer = await self._current_session_pointer(
                    session.name,
                )
                await self._apply_bound_model_profile_for_role(
                    role_name_from_metadata(session.metadata),
                )
                expected_model_profile_revision = int(
                    getattr(self._runtime, "model_profile_revision", 0),
                )
            if route_mode is not None:
                session = await self._runtime.chat_service.set_route_mode(
                    session.name,
                    route_mode,
                )
                expected_current_pointer = await self._current_session_pointer(
                    session.name,
                )

            if channel_type or channel_integration_id:
                session = await self._set_channel_binding_unlocked(
                    session.name,
                    channel_type=channel_type,
                    channel_integration_id=channel_integration_id,
                )
            return session
        except BaseException as original_error:
            rollback_errors: list[Exception] = []
            try:
                await self._restore_runtime_snapshot(
                    snapshot,
                    expected_current_pointer=expected_current_pointer,
                    expected_model_profile_revision=(
                        expected_model_profile_revision
                    ),
                )
            except Exception as error:
                rollback_errors.append(error)
            if session is not None:
                try:
                    await self._runtime.session_service.delete_session(session.name)
                except Exception as error:
                    rollback_errors.append(error)
            if rollback_errors:
                raise RuntimeError(
                    "Session creation failed and rollback was incomplete",
                ) from original_error
            raise

    async def load_session(self, session_name: str):
        return await self._runtime.session_service.load_session(session_name)

    async def rename_session(self, session_name: str, next_name: str):
        session = await self._runtime.session_service.rename_session(
            session_name,
            next_name,
        )
        await notify_session_runtime_context_changed(
            self._runtime,
            session_name,
            reason="session_renamed",
            metadata={"new_session_name": session.name},
        )
        if session.name != session_name:
            await notify_session_runtime_context_changed(
                self._runtime,
                session.name,
                reason="session_renamed",
            )
        return session

    async def set_role(self, session_name: str, role_name: str):
        # Role switching historically creates the named Session on first use.
        # Resolve it before conflict validation so that compatibility remains
        # intact without mutating role metadata before the binding check passes.
        normalized_role_name = self._require_role(role_name)
        async with self._runtime.session_binding_lock:
            session_lock = await self._runtime.session_service.session_lock(session_name)
            async with session_lock:
                session = await self._set_role_transaction(
                    session_name,
                    normalized_role_name,
                )
        await notify_session_runtime_context_changed(
            self._runtime,
            session.name,
            reason="session_role_updated",
        )
        return session

    async def _set_role_transaction(
        self,
        session_name: str,
        normalized_role_name: str,
    ):
        snapshot = await self._capture_runtime_snapshot()
        expected_current_pointer: tuple[str, int] | None = None
        expected_model_profile_revision = snapshot.model_profile_revision
        current_session = None
        session_mutated = False
        previous_role_name = "default"
        previous_channel_type = ""
        previous_channel_integration_id = ""
        added_default_binding = False
        try:
            try:
                current_session = await self._runtime.session_service.load_session(
                    session_name,
                )
            except ValueError:
                current_session = None
            if current_session is not None:
                previous_role_name = role_name_from_metadata(current_session.metadata)
                previous_channel_type = channel_type_from_metadata(
                    current_session.metadata,
                )
                previous_channel_integration_id = channel_integration_id_from_metadata(
                    current_session.metadata,
                )

            next_channel_type = ""
            next_channel_integration_id = ""
            if current_session is None or not (
                previous_channel_type or previous_channel_integration_id
            ):
                (
                    next_channel_type,
                    next_channel_integration_id,
                ) = await self._default_channel_binding_for_role(normalized_role_name)
                await self._assert_channel_binding_available(
                    channel_type=next_channel_type,
                    channel_integration_id=next_channel_integration_id,
                    excluding_session_name=(
                        current_session.name
                        if current_session is not None
                        else session_name
                    ),
                )

            session = await self._runtime.chat_service.set_role(
                session_name,
                normalized_role_name,
            )
            session_mutated = True
            expected_current_pointer = await self._current_session_pointer(session.name)
            if next_channel_type or next_channel_integration_id:
                session = await self._set_channel_binding_unlocked(
                    session.name,
                    channel_type=next_channel_type,
                    channel_integration_id=next_channel_integration_id,
                )
                added_default_binding = True
            resolved_role_name = role_name_from_metadata(session.metadata)
            await self._apply_bound_model_profile_for_role(resolved_role_name)
            expected_model_profile_revision = int(
                getattr(self._runtime, "model_profile_revision", 0),
            )
            return session
        except BaseException as original_error:
            rollback_errors: list[Exception] = []
            if session_mutated and current_session is None:
                try:
                    await self._restore_runtime_snapshot(
                        snapshot,
                        expected_current_pointer=expected_current_pointer,
                        expected_model_profile_revision=(
                            expected_model_profile_revision
                        ),
                    )
                except Exception as error:
                    rollback_errors.append(error)
                try:
                    await self._runtime.session_service.delete_session(session_name)
                except Exception as error:
                    rollback_errors.append(error)
            elif session_mutated:
                try:
                    await self._runtime.session_service.update_session_metadata(
                        session_name,
                        lambda metadata: self._restore_role_metadata(
                            metadata,
                            role_name=previous_role_name,
                            restore_channel_binding=added_default_binding,
                            channel_type=previous_channel_type,
                            channel_integration_id=previous_channel_integration_id,
                        ),
                    )
                except Exception as error:
                    rollback_errors.append(error)
                try:
                    await self._restore_runtime_snapshot(
                        snapshot,
                        expected_current_pointer=expected_current_pointer,
                        expected_model_profile_revision=(
                            expected_model_profile_revision
                        ),
                    )
                except Exception as error:
                    rollback_errors.append(error)
            else:
                try:
                    await self._restore_runtime_snapshot(
                        snapshot,
                        expected_model_profile_revision=(
                            expected_model_profile_revision
                        ),
                    )
                except Exception as error:
                    rollback_errors.append(error)
            if rollback_errors:
                raise RuntimeError(
                    "Session role update failed and rollback was incomplete",
                ) from original_error
            raise

    def _require_role(self, role_name: str) -> str:
        context = getattr(self._runtime, "context", None)
        registry = getattr(context, "role_registry", None)
        if registry is None:
            raise RuntimeError("Role registry is not ready")
        return registry.require(role_name).name

    @staticmethod
    def _restore_role_metadata(
        metadata,
        *,
        role_name: str,
        restore_channel_binding: bool,
        channel_type: str,
        channel_integration_id: str,
    ):
        restored = set_role_name(metadata, role_name)
        if not restore_channel_binding:
            return restored
        return set_channel_binding(
            restored,
            channel_type=channel_type,
            channel_integration_id=channel_integration_id,
        )

    async def set_route_mode(self, session_name: str, route_mode):
        session = await self._runtime.chat_service.set_route_mode(
            session_name,
            route_mode,
        )
        await notify_session_runtime_context_changed(
            self._runtime,
            session.name,
            reason="session_route_mode_updated",
        )
        return session

    async def set_channel_binding(
        self,
        session_name: str,
        *,
        channel_type: str,
        channel_integration_id: str,
    ):
        async with self._runtime.session_binding_lock:
            await self._assert_channel_binding_available(
                channel_type=channel_type,
                channel_integration_id=channel_integration_id,
                excluding_session_name=session_name,
            )
            session = await self._set_channel_binding_unlocked(
                session_name,
                channel_type=channel_type,
                channel_integration_id=channel_integration_id,
            )
        await notify_session_runtime_context_changed(
            self._runtime,
            session.name,
            reason="session_channel_binding_updated",
        )
        return session

    async def update_configuration(
        self,
        session_name: str,
        *,
        role_name: str,
        route_mode,
        channel_type: str,
        channel_integration_id: str,
    ):
        """Validate and persist one complete Session configuration in one write."""
        normalized_role_name = self._require_role(role_name)
        next_channel_type = str(channel_type or "").strip()
        next_channel_integration_id = str(channel_integration_id or "").strip()
        async with self._runtime.session_binding_lock:
            await self._runtime.session_service.load_session(session_name)
            await self._assert_channel_binding_available(
                channel_type=next_channel_type,
                channel_integration_id=next_channel_integration_id,
                excluding_session_name=session_name,
            )
            session = await self._runtime.session_service.update_session_metadata(
                session_name,
                lambda metadata: self._configured_session_metadata(
                    metadata,
                    role_name=normalized_role_name,
                    route_mode=route_mode,
                    channel_type=next_channel_type,
                    channel_integration_id=next_channel_integration_id,
                ),
            )
        await notify_session_runtime_context_changed(
            self._runtime,
            session.name,
            reason="session_configuration_updated",
        )
        return session

    @staticmethod
    def _configured_session_metadata(
        metadata,
        *,
        role_name: str,
        route_mode,
        channel_type: str,
        channel_integration_id: str,
    ):
        next_metadata = set_role_name(metadata, role_name)
        next_metadata = set_route_mode(next_metadata, route_mode)
        return set_channel_binding(
            next_metadata,
            channel_type=channel_type,
            channel_integration_id=channel_integration_id,
        )

    async def _set_channel_binding_unlocked(
        self,
        session_name: str,
        *,
        channel_type: str,
        channel_integration_id: str,
    ):
        return await self._runtime.session_service.update_session_metadata(
            session_name,
            lambda metadata: set_channel_binding(
                metadata,
                channel_type=channel_type,
                channel_integration_id=channel_integration_id,
            ),
        )

    async def delete_session(self, session_name: str) -> bool:
        deleted = await self._runtime.session_service.delete_session(session_name)
        if deleted:
            await notify_session_runtime_context_changed(
                self._runtime,
                session_name,
                reason="session_deleted",
            )
        return deleted

    async def _apply_bound_model_profile_for_role(self, role_name: str) -> None:
        await apply_runtime_profile_for_role(
            self._runtime,
            role_name,
        )

    async def _capture_runtime_snapshot(self) -> _RuntimeMutationSnapshot:
        current_session_name, current_session_revision = (
            await self._runtime.session_service.get_current_session_pointer()
        )

        active_profile_id = ""
        model_profiles = getattr(self._runtime, "model_profile_service", None)
        model_profile_lock = getattr(self._runtime, "model_profile_lock", None)
        if model_profile_lock is None:
            raise RuntimeError("Runtime model profile lock is not configured")
        async with model_profile_lock:
            if model_profiles is not None:
                state = await asyncio.to_thread(model_profiles.list_profiles)
                active_profile_id = str(state.get("active_profile_id") or "")
            applied_model_profile = deepcopy(
                getattr(self._runtime, "last_applied_model_profile", {}) or {},
            )
            model_profile_revision = int(
                getattr(self._runtime, "model_profile_revision", 0),
            )

        return _RuntimeMutationSnapshot(
            current_session_name=str(current_session_name or ""),
            current_session_revision=current_session_revision,
            active_profile_id=active_profile_id,
            applied_model_profile=applied_model_profile,
            model_profile_revision=model_profile_revision,
        )

    async def _restore_runtime_snapshot(
        self,
        snapshot: _RuntimeMutationSnapshot,
        *,
        expected_current_pointer: tuple[str, int] | None = None,
        expected_model_profile_revision: int,
    ) -> None:
        rollback_errors: list[Exception] = []
        model_profiles = getattr(self._runtime, "model_profile_service", None)
        model_profile_lock = getattr(self._runtime, "model_profile_lock", None)
        if model_profile_lock is None:
            rollback_errors.append(
                RuntimeError("Runtime model profile lock is not configured"),
            )
        else:
            async with model_profile_lock:
                current_model_revision = int(
                    getattr(self._runtime, "model_profile_revision", 0),
                )
                if current_model_revision == expected_model_profile_revision:
                    profile_state_changed = False
                    if model_profiles is not None and snapshot.active_profile_id:
                        try:
                            await asyncio.to_thread(
                                model_profiles.activate_profile,
                                snapshot.active_profile_id,
                            )
                            profile_state_changed = True
                        except Exception as error:
                            rollback_errors.append(error)

                    if snapshot.applied_model_profile:
                        try:
                            await self._runtime.apply_model_profile(
                                deepcopy(snapshot.applied_model_profile),
                            )
                        except Exception as error:
                            rollback_errors.append(error)
                    elif profile_state_changed:
                        self._runtime.model_profile_revision += 1

        if expected_current_pointer is not None:
            try:
                expected_name, expected_revision = expected_current_pointer
                await self._runtime.session_service.compare_and_set_current_session(
                    expected_name,
                    snapshot.current_session_name or None,
                    expected_revision=expected_revision,
                )
            except Exception as error:
                rollback_errors.append(error)

        if rollback_errors:
            raise RuntimeError("Runtime rollback was incomplete") from rollback_errors[0]

    async def _current_session_pointer(
        self,
        expected_session_name: str,
    ) -> tuple[str, int]:
        current_name, revision = (
            await self._runtime.session_service.get_current_session_pointer()
        )
        if current_name != expected_session_name:
            raise RuntimeError(
                "Current Session pointer changed during Session mutation",
            )
        return current_name, revision

    async def _default_channel_binding_for_role(
        self,
        role_name: str,
    ) -> tuple[str, str]:
        bindings = await runtime_bindings_for_role(self._runtime, role_name)
        return (
            str(bindings.get("default_channel_type") or "").strip(),
            str(bindings.get("default_channel_integration_id") or "").strip(),
        )

    async def _assert_channel_binding_available(
        self,
        *,
        channel_type: str,
        channel_integration_id: str,
        excluding_session_name: str = "",
    ) -> None:
        if not str(channel_type or "").strip() and not str(
            channel_integration_id or "",
        ).strip():
            return

        excluded = str(excluding_session_name or "").strip().lower()
        for item in await self._runtime.session_service.list_sessions():
            if str(item.name or "").strip().lower() == excluded:
                continue
            try:
                session = await self._runtime.session_service.load_session(item.name)
            except ValueError:
                continue
            if channel_bindings_overlap(
                session.metadata,
                channel_type=channel_type,
                channel_integration_id=channel_integration_id,
            ):
                raise ChannelBindingConflictError(
                    f"Channel integration is already bound to Session: {session.name}",
                )
