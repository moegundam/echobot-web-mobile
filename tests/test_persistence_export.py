from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from echobot.persistence.export import build_postgres_seed_export, write_postgres_seed_export
from echobot.persistence.postgres_schema import POSTGRES_SCHEMA_SQL
from echobot.runtime.sessions import SessionStore


class PostgresMigrationExportTests(unittest.TestCase):
    def test_schema_contains_session_centered_tables(self) -> None:
        self.assertIn("create table if not exists sessions", POSTGRES_SCHEMA_SQL)
        self.assertIn("create table if not exists characters", POSTGRES_SCHEMA_SQL)
        self.assertIn("create table if not exists channel_integrations", POSTGRES_SCHEMA_SQL)
        self.assertIn("owner_user_id", POSTGRES_SCHEMA_SQL)

    def test_seed_export_redacts_channel_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            storage_root = workspace / ".echobot"
            store = SessionStore(storage_root / "sessions")
            session = store.create_session("demo")
            session.metadata["channel_type"] = "telegram"
            store.save_session(session)
            (storage_root / "channels.json").write_text(
                json.dumps(
                    {
                        "telegram": {
                            "enabled": True,
                            "bot_token": "telegram-secret",
                            "mirror_to_stage": True,
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (storage_root / "llm_models.json").write_text(
                json.dumps({"active_model_id": "a", "models": {"a": {"model": "safe"}}}),
                encoding="utf-8",
            )
            (storage_root / "voice_profile_secrets.json").write_text(
                json.dumps({"profiles": {"a": {"tts": {"api_key": "voice-secret"}}}}),
                encoding="utf-8",
            )

            payload = build_postgres_seed_export(workspace)
            output = workspace / "seed.json"
            write_postgres_seed_export(workspace, output)

            self.assertEqual("echobot-postgres-seed-v1", payload["format"])
            self.assertEqual("demo", payload["sessions"][0]["name"])
            self.assertEqual("safe", payload["llm_models"]["models"]["a"]["model"])
            self.assertEqual({}, payload["voice_profiles"])
            self.assertEqual("", payload["channels"]["telegram"]["bot_token"])
            self.assertTrue(payload["channels"]["telegram"]["bot_token_configured"])
            self.assertNotIn("telegram-secret", output.read_text(encoding="utf-8"))
            self.assertNotIn("voice-secret", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
