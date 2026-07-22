from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from echobot.app.services.user_runtime_factory import (
    RuntimeStopError,
    UserRuntimeFactory,
)


class _FakeRuntime:
    def __init__(self, name: str, *, fail_on_stop: bool = False) -> None:
        self.name = name
        self.fail_on_stop = fail_on_stop
        self.stop_calls = 0
        self.stopped = asyncio.Event()

    async def stop(self) -> None:
        self.stop_calls += 1
        self.stopped.set()
        if self.fail_on_stop:
            raise RuntimeError(f"stop failed: {self.name}")


def _run(coro):
    return asyncio.run(coro)


def test_factory_evicts_least_recently_used_runtime_and_awaits_stop(tmp_path: Path) -> None:
    async def scenario() -> None:
        created: list[_FakeRuntime] = []

        async def build(user_id: str, _storage_root: Path) -> _FakeRuntime:
            runtime = _FakeRuntime(user_id)
            created.append(runtime)
            return runtime

        factory = UserRuntimeFactory(
            workspace_getter=lambda: tmp_path,
            runtime_builder=build,
            max_entries=2,
            idle_ttl_seconds=None,
        )

        first = await factory.for_user("one@example.test")
        second = await factory.for_user("two@example.test")
        assert await factory.for_user("one@example.test") is first

        third = await factory.for_user("three@example.test")

        assert third is created[2]
        assert second.stop_calls == 1
        assert second.stopped.is_set()
        assert factory.cached_runtimes() == (first, third)

    _run(scenario())


def test_factory_evicts_idle_runtimes_during_request_time_cleanup(tmp_path: Path) -> None:
    async def scenario() -> None:
        now = 100.0
        created: list[_FakeRuntime] = []

        async def build(user_id: str, _storage_root: Path) -> _FakeRuntime:
            runtime = _FakeRuntime(user_id)
            created.append(runtime)
            return runtime

        def clock() -> float:
            return now

        factory = UserRuntimeFactory(
            workspace_getter=lambda: tmp_path,
            runtime_builder=build,
            max_entries=4,
            idle_ttl_seconds=10.0,
            clock=clock,
        )

        first = await factory.for_user("one@example.test")
        now = 109.0
        assert await factory.for_user("one@example.test") is first
        now = 120.0
        second = await factory.for_user("two@example.test")

        assert second is created[1]
        assert first.stop_calls == 1
        assert factory.cached_runtimes() == (second,)

    _run(scenario())


def test_factory_deduplicates_same_key_concurrent_builds(tmp_path: Path) -> None:
    async def scenario() -> None:
        build_started = asyncio.Event()
        release_build = asyncio.Event()
        build_count = 0

        async def build(user_id: str, _storage_root: Path) -> _FakeRuntime:
            nonlocal build_count
            build_count += 1
            build_started.set()
            await release_build.wait()
            return _FakeRuntime(user_id)

        factory = UserRuntimeFactory(
            workspace_getter=lambda: tmp_path,
            runtime_builder=build,
            max_entries=2,
            idle_ttl_seconds=None,
        )

        first_task = asyncio.create_task(factory.for_user("same@example.test"))
        await build_started.wait()
        second_task = asyncio.create_task(factory.for_user("same@example.test"))
        await asyncio.sleep(0)
        release_build.set()

        first, second = await asyncio.gather(first_task, second_task)
        assert first is second
        assert build_count == 1

    _run(scenario())


def test_factory_builds_different_users_concurrently(tmp_path: Path) -> None:
    async def scenario() -> None:
        both_started = asyncio.Event()
        release = asyncio.Event()
        started: set[str] = set()

        async def build(user_id: str, _storage_root: Path) -> _FakeRuntime:
            started.add(user_id)
            if len(started) == 2:
                both_started.set()
            await release.wait()
            return _FakeRuntime(user_id)

        factory = UserRuntimeFactory(
            workspace_getter=lambda: tmp_path,
            runtime_builder=build,
            max_entries=2,
            idle_ttl_seconds=None,
        )
        first = asyncio.create_task(factory.for_user("one@example.test"))
        second = asyncio.create_task(factory.for_user("two@example.test"))

        await asyncio.wait_for(both_started.wait(), timeout=1)
        release.set()
        await asyncio.gather(first, second)

        assert started == {"one@example.test", "two@example.test"}

    _run(scenario())


def test_stop_all_attempts_every_runtime_clears_cache_and_is_idempotent(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        runtimes: dict[str, _FakeRuntime] = {}

        async def build(user_id: str, _storage_root: Path) -> _FakeRuntime:
            runtime = _FakeRuntime(user_id, fail_on_stop=user_id == "bad@example.test")
            runtimes[user_id] = runtime
            return runtime

        factory = UserRuntimeFactory(
            workspace_getter=lambda: tmp_path,
            runtime_builder=build,
            max_entries=3,
            idle_ttl_seconds=None,
        )
        await factory.for_user("bad@example.test")
        await factory.for_user("good@example.test")

        with pytest.raises(RuntimeStopError) as error:
            await factory.stop_all()

        assert "bad@example.test" in str(error.value)
        assert runtimes["bad@example.test"].stop_calls == 1
        assert runtimes["good@example.test"].stop_calls == 1
        assert factory.cached_runtimes() == ()

        await factory.stop_all()

    _run(scenario())


def test_builder_failure_is_not_cached_and_can_retry(tmp_path: Path) -> None:
    async def scenario() -> None:
        attempts = 0

        async def build(user_id: str, _storage_root: Path) -> _FakeRuntime:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient build failure")
            return _FakeRuntime(user_id)

        factory = UserRuntimeFactory(
            workspace_getter=lambda: tmp_path,
            runtime_builder=build,
            max_entries=2,
            idle_ttl_seconds=None,
        )

        with pytest.raises(RuntimeError, match="transient build failure"):
            await factory.for_user("retry@example.test")

        runtime = await factory.for_user("retry@example.test")
        assert runtime.name == "retry@example.test"
        assert attempts == 2
        assert factory.cached_runtimes() == (runtime,)

    _run(scenario())


def test_concurrent_stop_all_stops_each_runtime_once(tmp_path: Path) -> None:
    async def scenario() -> None:
        created: list[_FakeRuntime] = []

        async def build(user_id: str, _storage_root: Path) -> _FakeRuntime:
            runtime = _FakeRuntime(user_id)
            created.append(runtime)
            return runtime

        factory = UserRuntimeFactory(
            workspace_getter=lambda: tmp_path,
            runtime_builder=build,
            max_entries=2,
            idle_ttl_seconds=None,
        )
        await factory.for_user("one@example.test")
        await factory.for_user("two@example.test")

        await asyncio.gather(factory.stop_all(), factory.stop_all())

        assert [runtime.stop_calls for runtime in created] == [1, 1]
        assert factory.cached_runtimes() == ()

    _run(scenario())


def test_factory_reads_bounded_defaults_from_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ECHOBOT_USER_RUNTIME_MAX_ENTRIES", "12")
    monkeypatch.setenv("ECHOBOT_USER_RUNTIME_IDLE_TTL_SECONDS", "900")

    factory = UserRuntimeFactory(
        workspace_getter=lambda: tmp_path,
        runtime_builder=lambda _user_id, _storage_root: _never_called(),
    )

    assert factory.max_entries == 12
    assert factory.idle_ttl_seconds == 900.0


def test_factory_rejects_invalid_environment_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in (
        ("ECHOBOT_USER_RUNTIME_MAX_ENTRIES", "0"),
        ("ECHOBOT_USER_RUNTIME_MAX_ENTRIES", "many"),
        ("ECHOBOT_USER_RUNTIME_IDLE_TTL_SECONDS", "-1"),
        ("ECHOBOT_USER_RUNTIME_IDLE_TTL_SECONDS", "nan"),
    ):
        monkeypatch.delenv("ECHOBOT_USER_RUNTIME_MAX_ENTRIES", raising=False)
        monkeypatch.delenv("ECHOBOT_USER_RUNTIME_IDLE_TTL_SECONDS", raising=False)
        monkeypatch.setenv(key, value)
        with pytest.raises(ValueError, match=key):
            UserRuntimeFactory(
                workspace_getter=lambda: tmp_path,
                runtime_builder=lambda _user_id, _storage_root: _never_called(),
            )


async def _never_called() -> _FakeRuntime:
    raise AssertionError("runtime builder should not be called")
