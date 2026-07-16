from __future__ import annotations

import unittest

from echobot.persistence.postgres_schema import POSTGRES_SCHEMA_SQL


class PostgresChannelBindingSchemaTests(unittest.TestCase):
    def test_session_binding_guard_matches_runtime_normalization(self) -> None:
        self.assertIn("channel_type channel_type", POSTGRES_SCHEMA_SQL)
        self.assertIn("echobot_normalize_channel_binding", POSTGRES_SCHEMA_SQL)
        self.assertIn(r"\00A0", POSTGRES_SCHEMA_SQL)
        self.assertIn(r"\3000", POSTGRES_SCHEMA_SQL)
        self.assertIn(r"\000B", POSTGRES_SCHEMA_SQL)
        self.assertNotIn(r"E' \\t\\n\\r\\f\\v'", POSTGRES_SCHEMA_SQL)
        self.assertIn(
            "echobot_enforce_session_channel_binding_uniqueness",
            POSTGRES_SCHEMA_SQL,
        )
        self.assertIn("pg_advisory_xact_lock", POSTGRES_SCHEMA_SQL)
        self.assertIn("transaction_isolation') = 'repeatable read'", POSTGRES_SCHEMA_SQL)
        self.assertIn("channel binding conflicts with session", POSTGRES_SCHEMA_SQL)


if __name__ == "__main__":
    unittest.main()
