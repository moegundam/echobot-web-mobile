from __future__ import annotations

import asyncio
import sys
import textwrap
import unittest
from types import SimpleNamespace
from typing import Any

from echobot.app.routers.stage import subscribe_stage_events
from echobot.app.services.stage_event_redis import RedisStreamsStageEventBroker
from echobot.app.services.stage_events import (
    StageEventBroker,
    StageEventBrokerCapacityError,
    StageEventBrokerProtocol,
    StageEventPublishRequest,
    StageEventSubscriptionProtocol,
    stage_event_to_sse,
)


class FakeRedisStreamsClient:
    def __init__(self) -> None:
        self.entries: dict[
            str,
            list[tuple[bytes, dict[bytes, bytes]]],
        ] = {}
        self.xadd_calls: list[dict[str, Any]] = []
        self.expire_calls: list[dict[str, Any]] = []
        self._next_ids: dict[str, int] = {}

    async def xadd(
        self,
        name: str,
        fields: dict[str, str],
        *,
        maxlen: int,
        approximate: bool,
    ) -> bytes:
        next_id = self._next_ids.get(name, 1)
        stream_id = f"{next_id}-0".encode()
        self._next_ids[name] = next_id + 1
        encoded_fields = {
            str(key).encode(): str(value).encode()
            for key, value in fields.items()
        }
        stream_entries = self.entries.setdefault(name, [])
        stream_entries.append((stream_id, encoded_fields))
        if len(stream_entries) > maxlen:
            self.entries[name] = stream_entries[-maxlen:]
        self.xadd_calls.append(
            {
                "name": name,
                "fields": fields,
                "maxlen": maxlen,
                "approximate": approximate,
            },
        )
        return stream_id

    async def expire(self, name: str, seconds: int) -> bool:
        self.expire_calls.append({"name": name, "seconds": seconds})
        return True

    async def xrevrange(
        self,
        name: str,
        *,
        count: int,
    ) -> list[tuple[bytes, dict[bytes, bytes]]]:
        return list(reversed(self.entries.get(name, [])))[:count]

    async def xrange(
        self,
        name: str,
        *,
        min: str,
        max: str,
        count: int,
    ) -> list[tuple[bytes, dict[bytes, bytes]]]:
        return [
            entry
            for entry in self.entries.get(name, [])
            if min <= entry[0].decode() <= max
        ][:count]

    async def xread(
        self,
        streams: dict[str, str],
        *,
        count: int,
        block: int,
    ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
        del block
        name, cursor = next(iter(streams.items()))
        cursor_parts = tuple(int(part) for part in cursor.split("-", 1))
        entries = [
            entry
            for entry in self.entries.get(name, [])
            if tuple(int(part) for part in entry[0].decode().split("-", 1))
            > cursor_parts
        ][:count]
        if not entries:
            return []
        return [(name.encode(), entries)]

    def texts(self, name: str) -> list[str]:
        return [
            fields[b"text"].decode()
            for _, fields in self.entries.get(name, [])
        ]


class StageEventBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_broker_and_subscription_implement_explicit_protocols(self) -> None:
        broker = StageEventBroker()
        subscription = await broker.subscribe(
            scope_key="alpha",
            session_name="demo",
            replay_history=False,
        )
        try:
            self.assertIsInstance(broker, StageEventBrokerProtocol)
            self.assertIsInstance(subscription, StageEventSubscriptionProtocol)
        finally:
            await subscription.close()

    async def test_events_are_scoped_by_user_and_session(self) -> None:
        broker = StageEventBroker(history_limit=10, queue_limit=2)

        event = await broker.publish(
            scope_key="alpha",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="hello stage",
                speaker="Echo",
                source="messenger",
            ),
        )

        self.assertRegex(event.event_id, r"^evt_[A-Za-z0-9_-]+$")
        self.assertEqual("demo", event.session_name)
        self.assertEqual(["hello stage"], [item.text for item in broker.history("alpha", "demo")])
        self.assertEqual([], broker.history("beta", "demo"))
        self.assertEqual([], broker.history("alpha", "other"))

    async def test_subscriber_queue_drops_oldest_event_when_full(self) -> None:
        broker = StageEventBroker(history_limit=10, queue_limit=1)

        subscription = await broker.subscribe(
            scope_key="alpha",
            session_name="demo",
            replay_history=False,
        )
        try:
            await broker.publish(
                scope_key="alpha",
                request=StageEventPublishRequest(
                    kind="assistant_delta",
                    session_name="demo",
                    text="first",
                    source="messenger",
                ),
            )
            await broker.publish(
                scope_key="alpha",
                request=StageEventPublishRequest(
                    kind="assistant_final",
                    session_name="demo",
                    text="second",
                    source="messenger",
                ),
            )

            event = await asyncio.wait_for(subscription.next_event(), timeout=0.2)
        finally:
            await subscription.close()

        self.assertEqual("second", event.text)
        self.assertEqual("drop_oldest", subscription.pressure_policy)
        self.assertEqual(1, subscription.dropped_event_count)

    async def test_history_and_channel_keys_are_bounded_with_idle_lru_eviction(self) -> None:
        broker = StageEventBroker(history_limit=2, max_channels=2)

        for text in ("alpha-1", "alpha-2", "alpha-3"):
            await broker.publish(
                scope_key="alpha",
                request=StageEventPublishRequest(
                    kind="assistant_delta",
                    session_name="demo",
                    text=text,
                ),
            )
        await broker.publish(
            scope_key="beta",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="beta",
            ),
        )

        self.assertEqual(
            ["alpha-2", "alpha-3"],
            [event.text for event in broker.history("alpha", "demo")],
        )

        await broker.publish(
            scope_key="gamma",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="gamma",
            ),
        )

        self.assertEqual(2, broker.channel_count)
        self.assertEqual([], broker.history("beta", "demo"))
        self.assertEqual(
            ["alpha-2", "alpha-3"],
            [event.text for event in broker.history("alpha", "demo")],
        )
        self.assertEqual(
            ["gamma"],
            [event.text for event in broker.history("gamma", "demo")],
        )

    async def test_new_channel_is_rejected_when_all_bounded_channels_are_active(self) -> None:
        broker = StageEventBroker(max_channels=1)
        subscription = await broker.subscribe(
            scope_key="alpha",
            session_name="demo",
            replay_history=False,
        )
        try:
            with self.assertRaisesRegex(StageEventBrokerCapacityError, "capacity"):
                await broker.subscribe(
                    scope_key="beta",
                    session_name="demo",
                    replay_history=False,
                )
        finally:
            await subscription.close()

        await broker.publish(
            scope_key="beta",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="accepted after close",
            ),
        )
        self.assertEqual([], broker.history("alpha", "demo"))
        self.assertEqual(
            ["accepted after close"],
            [event.text for event in broker.history("beta", "demo")],
        )

    async def test_subscribe_replays_only_events_after_known_cursor(self) -> None:
        broker = StageEventBroker(history_limit=10, queue_limit=10)
        first = await broker.publish(
            scope_key="alpha",
            request=StageEventPublishRequest(
                kind="assistant_delta",
                session_name="demo",
                text="first",
            ),
        )
        for text in ("second", "third"):
            await broker.publish(
                scope_key="alpha",
                request=StageEventPublishRequest(
                    kind="assistant_delta",
                    session_name="demo",
                    text=text,
                ),
            )

        subscription = await broker.subscribe(
            scope_key="alpha",
            session_name="demo",
            replay_history=True,
            after_event_id=first.event_id,
        )
        try:
            replayed = [
                await asyncio.wait_for(subscription.next_event(), timeout=0.2),
                await asyncio.wait_for(subscription.next_event(), timeout=0.2),
            ]
        finally:
            await subscription.close()

        self.assertEqual(["second", "third"], [event.text for event in replayed])

    async def test_stale_cursor_replays_all_retained_history(self) -> None:
        broker = StageEventBroker(history_limit=2, queue_limit=2)
        first = await broker.publish(
            scope_key="alpha",
            request=StageEventPublishRequest(
                kind="assistant_delta",
                session_name="demo",
                text="first",
            ),
        )
        for text in ("second", "third"):
            await broker.publish(
                scope_key="alpha",
                request=StageEventPublishRequest(
                    kind="assistant_delta",
                    session_name="demo",
                    text=text,
                ),
            )

        subscription = await broker.subscribe(
            scope_key="alpha",
            session_name="demo",
            after_event_id=first.event_id,
        )
        try:
            replayed = [
                await asyncio.wait_for(subscription.next_event(), timeout=0.2),
                await asyncio.wait_for(subscription.next_event(), timeout=0.2),
            ]
        finally:
            await subscription.close()

        self.assertEqual(["second", "third"], [event.text for event in replayed])

    async def test_recreated_broker_replays_new_event_for_old_cursor(self) -> None:
        old_broker = StageEventBroker()
        old_event = await old_broker.publish(
            scope_key="alpha",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="before restart",
            ),
        )
        recreated_broker = StageEventBroker()
        new_event = await recreated_broker.publish(
            scope_key="alpha",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="after restart",
            ),
        )

        self.assertNotEqual(old_event.event_id, new_event.event_id)
        subscription = await recreated_broker.subscribe(
            scope_key="alpha",
            session_name="demo",
            after_event_id=old_event.event_id,
        )
        try:
            replayed = await asyncio.wait_for(
                subscription.next_event(),
                timeout=0.2,
            )
        finally:
            await subscription.close()

        self.assertEqual(new_event.event_id, replayed.event_id)
        self.assertEqual("after restart", replayed.text)

    async def test_process_restart_replays_new_event_for_old_cursor(self) -> None:
        old_event = await StageEventBroker().publish(
            scope_key="alpha",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="before process restart",
            ),
        )
        restart_script = textwrap.dedent(
            """
            import asyncio
            import sys

            from echobot.app.services.stage_events import (
                StageEventBroker,
                StageEventPublishRequest,
            )

            async def main():
                broker = StageEventBroker()
                event = await broker.publish(
                    scope_key="alpha",
                    request=StageEventPublishRequest(
                        kind="assistant_final",
                        session_name="demo",
                        text="after process restart",
                    ),
                )
                subscription = await broker.subscribe(
                    scope_key="alpha",
                    session_name="demo",
                    after_event_id=sys.argv[1],
                )
                try:
                    replayed = await asyncio.wait_for(
                        subscription.next_event(),
                        timeout=0.2,
                    )
                finally:
                    await subscription.close()
                print(replayed.event_id)

            asyncio.run(main())
            """,
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            restart_script,
            old_event.event_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        self.assertEqual(0, process.returncode, stderr.decode())
        restarted_event_id = stdout.decode().strip()
        self.assertNotEqual(old_event.event_id, restarted_event_id)

    async def test_exact_latest_cursor_does_not_replay_delivered_event(self) -> None:
        broker = StageEventBroker()
        event = await broker.publish(
            scope_key="alpha",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="already delivered",
            ),
        )
        subscription = await broker.subscribe(
            scope_key="alpha",
            session_name="demo",
            after_event_id=event.event_id,
        )
        try:
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(subscription.next_event(), timeout=0.05)
        finally:
            await subscription.close()

    async def test_subscribe_replays_history_for_late_stage_viewer(self) -> None:
        broker = StageEventBroker(history_limit=10, queue_limit=2)

        await broker.publish(
            scope_key="alpha",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="ready for stage",
                source="messenger",
            ),
        )

        subscription = await broker.subscribe(
            scope_key="alpha",
            session_name="demo",
            replay_history=True,
        )
        try:
            event = await asyncio.wait_for(subscription.next_event(), timeout=0.2)
        finally:
            await subscription.close()

        self.assertEqual("assistant_final", event.kind)
        self.assertEqual("demo", event.session_name)
        self.assertEqual("ready for stage", event.text)

    async def test_stage_event_serializes_to_sse_payload(self) -> None:
        broker = StageEventBroker()
        event = await broker.publish(
            scope_key="alpha",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="hello stage",
                emotion="joy",
                expression="smile.exp3.json",
                motion="wave.motion3.json",
                source="messenger",
            ),
        )

        payload = stage_event_to_sse(event)

        self.assertIn(f"id: {event.event_id}", payload)
        self.assertIn("event: assistant_final", payload)
        self.assertIn('"text": "hello stage"', payload)
        self.assertIn('"emotion": "joy"', payload)
        self.assertIn('"expression": "smile.exp3.json"', payload)
        self.assertIn('"motion": "wave.motion3.json"', payload)

    async def test_stage_character_state_event_accepts_visual_directives_without_text(self) -> None:
        broker = StageEventBroker()
        event = await broker.publish(
            scope_key="alpha",
            request=StageEventPublishRequest(
                kind="character_state",
                session_name="demo",
                emotion="focused",
                expression="serious.exp3.json",
                motion="nod.motion3.json",
            ),
        )

        self.assertEqual("character_state", event.kind)
        self.assertEqual("", event.text)
        self.assertEqual("focused", event.emotion)
        self.assertEqual("serious.exp3.json", event.expression)
        self.assertEqual("nod.motion3.json", event.motion)

    async def test_stage_visual_directives_are_size_limited(self) -> None:
        broker = StageEventBroker()

        with self.assertRaisesRegex(ValueError, "Stage event expression is too large"):
            await broker.publish(
                scope_key="alpha",
                request=StageEventPublishRequest(
                    kind="character_state",
                    session_name="demo",
                    expression="x" * 257,
                ),
            )

    async def test_route_forwards_last_event_id_as_replay_cursor(self) -> None:
        broker = StageEventBroker(history_limit=10, queue_limit=10)
        first = await broker.publish(
            scope_key="default",
            request=StageEventPublishRequest(
                kind="assistant_delta",
                session_name="demo",
                text="first",
            ),
        )
        second = await broker.publish(
            scope_key="default",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="second",
            ),
        )
        runtime = SimpleNamespace(stage_event_broker=broker, user_id="")

        response = await subscribe_stage_events(
            session_name="demo",
            runtime=runtime,
            last_event_id=first.event_id,
        )
        iterator = response.body_iterator
        try:
            payload = await asyncio.wait_for(anext(iterator), timeout=0.2)
        finally:
            await iterator.aclose()

        self.assertIn(f"id: {second.event_id}", payload)
        self.assertNotIn(f"id: {first.event_id}", payload)

    async def test_redis_streams_adapter_isolates_bounded_expiring_streams(self) -> None:
        client = FakeRedisStreamsClient()
        factory_calls = 0
        stream_prefix = "echobot:test:stage-events"
        alpha_scope = "user:alpha@example.test"
        beta_scope = "user:beta@example.test"
        raw_primary_session = "Private Room"
        primary_session = "private-room"
        other_session = "second-room"

        def client_factory() -> FakeRedisStreamsClient:
            nonlocal factory_calls
            factory_calls += 1
            return client

        broker = RedisStreamsStageEventBroker(
            client_factory=client_factory,
            stream_key_prefix=stream_prefix,
            history_limit=2,
            queue_limit=4,
            stream_ttl_seconds=73,
        )
        self.assertEqual(0, factory_calls)
        self.assertIsInstance(broker, StageEventBrokerProtocol)

        beta_event = await broker.publish(
            scope_key=beta_scope,
            request=StageEventPublishRequest(
                kind="assistant_delta",
                session_name=primary_session,
                text="beta-retained",
            ),
        )
        first = await broker.publish(
            scope_key=alpha_scope,
            request=StageEventPublishRequest(
                kind="assistant_delta",
                session_name=raw_primary_session,
                text="alpha-first",
            ),
        )
        second = await broker.publish(
            scope_key=alpha_scope,
            request=StageEventPublishRequest(
                kind="assistant_delta",
                session_name=primary_session,
                text="alpha-second",
            ),
        )
        third = await broker.publish(
            scope_key=alpha_scope,
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name=primary_session,
                text="alpha-third",
                metadata={"language": "中文"},
            ),
        )
        await broker.publish(
            scope_key=alpha_scope,
            request=StageEventPublishRequest(
                kind="subtitle",
                session_name=other_session,
                text="other session",
            ),
        )

        subscription = await broker.subscribe(
            scope_key=alpha_scope,
            session_name=primary_session,
            after_event_id=second.event_id,
        )
        try:
            self.assertIsInstance(subscription, StageEventSubscriptionProtocol)
            replayed = await asyncio.wait_for(
                subscription.next_event(),
                timeout=0.2,
            )
        finally:
            await subscription.close()

        self.assertEqual(1, factory_calls)
        self.assertEqual(third.event_id, replayed.event_id)
        self.assertEqual("alpha-third", replayed.text)
        self.assertEqual({"language": "中文"}, replayed.metadata)

        stream_by_text = {
            call["fields"]["text"]: call["name"]
            for call in client.xadd_calls
        }
        alpha_stream = stream_by_text["alpha-first"]
        beta_stream = stream_by_text["beta-retained"]
        other_session_stream = stream_by_text["other session"]
        self.assertEqual(alpha_stream, stream_by_text["alpha-second"])
        self.assertEqual(alpha_stream, stream_by_text["alpha-third"])
        self.assertEqual(3, len(client.entries))
        self.assertEqual(3, len({alpha_stream, beta_stream, other_session_stream}))
        self.assertEqual(
            ["alpha-second", "alpha-third"],
            client.texts(alpha_stream),
        )
        self.assertEqual(["beta-retained"], client.texts(beta_stream))
        self.assertEqual(["other session"], client.texts(other_session_stream))
        self.assertEqual("1-0", beta_event.event_id)
        self.assertEqual("1-0", first.event_id)

        for stream_key in client.entries:
            self.assertTrue(stream_key.startswith(f"{stream_prefix}:"))
            hashes = stream_key.removeprefix(f"{stream_prefix}:").split(":")
            self.assertEqual(2, len(hashes))
            self.assertTrue(all(len(value) == 64 for value in hashes))
            self.assertTrue(
                all(set(value) <= set("0123456789abcdef") for value in hashes),
            )
            for raw_value in (
                alpha_scope,
                beta_scope,
                raw_primary_session,
                primary_session,
                other_session,
            ):
                self.assertNotIn(raw_value, stream_key)

        self.assertEqual(
            [call["name"] for call in client.xadd_calls],
            [call["name"] for call in client.expire_calls],
        )
        self.assertTrue(all(call["maxlen"] == 2 for call in client.xadd_calls))
        self.assertTrue(
            all(call["approximate"] is False for call in client.xadd_calls),
        )
        self.assertTrue(
            all(call["seconds"] == 73 for call in client.expire_calls),
        )

    async def test_redis_streams_adapter_requires_positive_stream_ttl(self) -> None:
        for invalid_ttl in (0, -1):
            with self.subTest(stream_ttl_seconds=invalid_ttl):
                with self.assertRaisesRegex(ValueError, "positive"):
                    RedisStreamsStageEventBroker(
                        client=FakeRedisStreamsClient(),
                        stream_ttl_seconds=invalid_ttl,
                    )

    async def test_redis_unknown_or_evicted_cursor_replays_retained_history(self) -> None:
        client = FakeRedisStreamsClient()
        broker = RedisStreamsStageEventBroker(
            client=client,
            history_limit=2,
            queue_limit=2,
        )
        for text in ("first", "second", "third"):
            await broker.publish(
                scope_key="alpha",
                request=StageEventPublishRequest(
                    kind="assistant_delta",
                    session_name="demo",
                    text=text,
                ),
            )

        subscription = await broker.subscribe(
            scope_key="alpha",
            session_name="demo",
            after_event_id="999-0",
        )
        try:
            replayed = [
                await asyncio.wait_for(subscription.next_event(), timeout=0.2),
                await asyncio.wait_for(subscription.next_event(), timeout=0.2),
            ]
        finally:
            await subscription.close()

        self.assertEqual(["second", "third"], [event.text for event in replayed])

    async def test_redis_streams_adapter_requires_client_only_when_used(self) -> None:
        broker = RedisStreamsStageEventBroker()

        with self.assertRaisesRegex(RuntimeError, "Redis client"):
            await broker.publish(
                scope_key="alpha",
                request=StageEventPublishRequest(
                    kind="assistant_final",
                    session_name="demo",
                    text="not published",
                ),
            )
