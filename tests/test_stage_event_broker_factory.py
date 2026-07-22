from __future__ import annotations

import unittest

from echobot.app.services.stage_event_broker_factory import (
    StageBrokerConfigurationError,
    StageEventBrokerConfig,
    create_stage_event_broker,
)
from echobot.app.services.stage_event_redis import RedisStreamsStageEventBroker
from echobot.app.services.stage_events import (
    StageEventBroker,
    StageEventBrokerProtocol,
)


class StageEventBrokerFactoryTests(unittest.TestCase):
    def test_defaults_to_memory_with_single_worker(self) -> None:
        config = StageEventBrokerConfig.from_env({})

        self.assertEqual("memory", config.backend)
        self.assertEqual(1, config.worker_count)
        broker = create_stage_event_broker(env={})

        self.assertIsInstance(broker, StageEventBroker)
        self.assertIsInstance(broker, StageEventBrokerProtocol)
        self.assertEqual(100, broker.history_limit)
        self.assertEqual(100, broker.queue_limit)
        self.assertEqual(256, broker.max_channels)
        self.assertEqual(15.0, broker.heartbeat_interval)

    def test_reads_all_memory_limits_from_environment(self) -> None:
        env = {
            "ECHOBOT_STAGE_BROKER": "memory",
            "ECHOBOT_STAGE_WORKER_COUNT": "1",
            "ECHOBOT_STAGE_HISTORY_LIMIT": "17",
            "ECHOBOT_STAGE_QUEUE_LIMIT": "19",
            "ECHOBOT_STAGE_MAX_CHANNELS": "23",
            "ECHOBOT_STAGE_HEARTBEAT_SECONDS": "2.5",
        }

        broker = create_stage_event_broker(env=env)

        self.assertEqual(17, broker.history_limit)
        self.assertEqual(19, broker.queue_limit)
        self.assertEqual(23, broker.max_channels)
        self.assertEqual(2.5, broker.heartbeat_interval)

    def test_memory_fails_closed_when_more_than_one_worker_is_configured(self) -> None:
        with self.assertRaisesRegex(
            StageBrokerConfigurationError,
            "ECHOBOT_STAGE_BROKER=redis.*ECHOBOT_STAGE_REDIS_URL",
        ):
            create_stage_event_broker(
                env={"ECHOBOT_STAGE_WORKER_COUNT": "2"},
            )

    def test_standard_worker_environment_also_enforces_the_memory_guard(self) -> None:
        for key in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(
                    StageBrokerConfigurationError,
                    "ECHOBOT_STAGE_BROKER=redis",
                ):
                    create_stage_event_broker(env={key: "2"})

    def test_redis_requires_a_url_even_when_no_client_is_injected(self) -> None:
        with self.assertRaisesRegex(
            StageBrokerConfigurationError,
            "ECHOBOT_STAGE_REDIS_URL",
        ):
            create_stage_event_broker(
                env={"ECHOBOT_STAGE_BROKER": "redis"},
            )

    def test_redis_factory_injects_client_without_connecting(self) -> None:
        client = object()
        env = {
            "ECHOBOT_STAGE_BROKER": "redis",
            "ECHOBOT_STAGE_REDIS_URL": "redis://stage.test/0",
            "ECHOBOT_STAGE_HISTORY_LIMIT": "31",
            "ECHOBOT_STAGE_QUEUE_LIMIT": "37",
            "ECHOBOT_STAGE_HEARTBEAT_SECONDS": "4.25",
            "ECHOBOT_STAGE_REDIS_TTL_SECONDS": "73",
            "ECHOBOT_STAGE_REDIS_READ_BLOCK_MS": "250",
        }

        broker = create_stage_event_broker(env=env, redis_client=client)

        self.assertIsInstance(broker, RedisStreamsStageEventBroker)
        self.assertIsInstance(broker, StageEventBrokerProtocol)
        self.assertIs(client, broker._client)
        self.assertEqual(31, broker.history_limit)
        self.assertEqual(37, broker.queue_limit)
        self.assertEqual(4.25, broker.heartbeat_interval)
        self.assertEqual(73, broker.stream_ttl_seconds)
        self.assertEqual(250, broker.read_block_ms)

    def test_unknown_backend_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            StageBrokerConfigurationError,
            "ECHOBOT_STAGE_BROKER",
        ):
            create_stage_event_broker(env={"ECHOBOT_STAGE_BROKER": "nats"})

    def test_invalid_integer_and_float_environment_values_are_rejected(self) -> None:
        invalid_values = {
            "ECHOBOT_STAGE_HISTORY_LIMIT": ("0", "-1", "1.0", "nan"),
            "ECHOBOT_STAGE_QUEUE_LIMIT": ("0", "-1", "1.0"),
            "ECHOBOT_STAGE_MAX_CHANNELS": ("0", "-1", "1.0"),
            "ECHOBOT_STAGE_WORKER_COUNT": ("0", "-1", "1.0"),
            "ECHOBOT_STAGE_REDIS_TTL_SECONDS": ("0", "-1", "1.5"),
            "ECHOBOT_STAGE_REDIS_READ_BLOCK_MS": ("0", "-1", "1.5"),
            "ECHOBOT_STAGE_HEARTBEAT_SECONDS": (
                "0",
                "-1",
                "nan",
                "inf",
                "not-a-number",
            ),
        }

        for key, values in invalid_values.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    with self.assertRaisesRegex(
                        StageBrokerConfigurationError,
                        key,
                    ):
                        create_stage_event_broker(env={key: value})


if __name__ == "__main__":
    unittest.main()
