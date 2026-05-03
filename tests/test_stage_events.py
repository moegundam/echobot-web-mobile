from __future__ import annotations

import asyncio
import unittest

from echobot.app.services.stage_events import (
    StageEventBroker,
    StageEventPublishRequest,
    stage_event_to_sse,
)


class StageEventBrokerTests(unittest.IsolatedAsyncioTestCase):
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

        self.assertEqual("evt_000001", event.event_id)
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

    async def test_stage_event_serializes_to_sse_payload(self) -> None:
        broker = StageEventBroker()
        event = await broker.publish(
            scope_key="alpha",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name="demo",
                text="hello stage",
                source="messenger",
            ),
        )

        payload = stage_event_to_sse(event)

        self.assertIn("id: evt_000001", payload)
        self.assertIn("event: assistant_final", payload)
        self.assertIn('"text": "hello stage"', payload)
