from __future__ import annotations

import tempfile
import unittest
import json
import stat
from pathlib import Path
from unittest.mock import patch

from echobot.app.services.model_profiles import ModelProfileService
from echobot.app.services.runtime_model_repositories import (
    LLMModelRepository,
    Live2DModelRepository,
    VoiceModelRepository,
)


class RuntimeModelCanonicalStoreTests(unittest.TestCase):
    def test_domain_stores_import_legacy_once_without_writing_it_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir) / ".echobot"
            legacy = ModelProfileService(storage_root)
            legacy.update_profile(
                "b",
                {
                    "label": "Imported profile",
                    "chat": {
                        "model": "legacy-chat",
                        "api_key": "legacy-chat-secret",
                    },
                    "tts": {"voice": "legacy-voice"},
                    "live2d": {"selection_key": "legacy-live2d"},
                },
            )
            legacy.activate_profile("b")

            legacy_store = storage_root / "model_profiles.json"
            legacy_secrets = storage_root / "model_profile_secrets.json"
            legacy_store_before = legacy_store.read_bytes()
            legacy_secrets_before = legacy_secrets.read_bytes()

            llm_repository = LLMModelRepository(legacy)
            voice_repository = VoiceModelRepository(legacy)
            live2d_repository = Live2DModelRepository(legacy)

            self.assertEqual("b", llm_repository.list_payload()["active_profile_id"])
            self.assertEqual("b", voice_repository.list_payload()["active_profile_id"])
            self.assertEqual("b", live2d_repository.list_payload()["active_profile_id"])

            llm_repository.update(
                "b",
                {
                    "model": "canonical-chat",
                    "api_key": "canonical-chat-secret",
                },
            )
            llm_repository.activate("a")
            voice_repository.update("b", {"tts": {"voice": "canonical-voice"}})
            live2d_repository.update(
                "b",
                {"selection_key": "canonical-live2d"},
            )

            self.assertEqual(legacy_store_before, legacy_store.read_bytes())
            self.assertEqual(legacy_secrets_before, legacy_secrets.read_bytes())

            reopened_llm = LLMModelRepository(legacy)
            reopened_voice = VoiceModelRepository(legacy)
            reopened_live2d = Live2DModelRepository(legacy)
            self.assertEqual(
                "canonical-chat",
                reopened_llm.get_runtime_profile("b")["chat"]["model"],
            )
            self.assertEqual(
                "canonical-chat-secret",
                reopened_llm.get_runtime_profile("b")["chat"]["api_key"],
            )
            self.assertEqual(
                "canonical-voice",
                reopened_voice.get_runtime_profile("b")["tts"]["voice"],
            )
            self.assertEqual(
                "canonical-live2d",
                reopened_live2d.get_runtime_profile("b")["live2d"]["selection_key"],
            )

    def test_domain_store_rolls_back_secret_when_public_commit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir) / ".echobot"
            repository = LLMModelRepository(ModelProfileService(storage_root))
            repository.update(
                "a",
                {"model": "before-model", "api_key": "before-secret"},
            )
            store = repository._store
            state_before = store._path.read_bytes()
            secrets_before = store._secret_path.read_bytes()

            with patch.object(
                store,
                "_save_state_unlocked",
                side_effect=OSError("injected public store failure"),
            ):
                with self.assertRaisesRegex(OSError, "injected public store failure"):
                    repository.update(
                        "a",
                        {"model": "after-model", "api_key": "after-secret"},
                    )

            self.assertEqual(state_before, store._path.read_bytes())
            self.assertEqual(secrets_before, store._secret_path.read_bytes())
            self.assertEqual(
                "before-model",
                repository.get_runtime_profile("a")["chat"]["model"],
            )
            self.assertEqual(
                "before-secret",
                repository.get_runtime_profile("a")["chat"]["api_key"],
            )
            self.assertEqual(0o600, stat.S_IMODE(store._secret_path.stat().st_mode))
            self.assertFalse(store._transaction_path.exists())

    def test_domain_store_recovers_committed_transaction_after_process_crash(self) -> None:
        class SimulatedProcessCrash(BaseException):
            pass

        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir) / ".echobot"
            legacy = ModelProfileService(storage_root)
            repository = LLMModelRepository(legacy)
            repository.update(
                "a",
                {"model": "before-model", "api_key": "before-secret"},
            )
            store = repository._store

            with patch.object(
                store,
                "_save_state_unlocked",
                side_effect=SimulatedProcessCrash,
            ):
                with self.assertRaises(SimulatedProcessCrash):
                    repository.update(
                        "a",
                        {"model": "after-model", "api_key": "after-secret"},
                    )

            self.assertTrue(store._transaction_path.exists())
            self.assertEqual(
                0o600,
                stat.S_IMODE(store._transaction_path.stat().st_mode),
            )

            reopened = LLMModelRepository(legacy)
            recovered = reopened.get_runtime_profile("a")
            self.assertEqual("after-model", recovered["chat"]["model"])
            self.assertEqual("after-secret", recovered["chat"]["api_key"])
            self.assertFalse(reopened._store._transaction_path.exists())

    def test_domain_store_atomic_replace_failure_preserves_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir) / ".echobot"
            repository = LLMModelRepository(ModelProfileService(storage_root))
            repository.list_payload()
            store = repository._store
            state_before = store._path.read_bytes()

            with patch(
                "echobot.app.services.runtime_model_repositories.os.replace",
                side_effect=OSError("injected replace failure"),
            ):
                with self.assertRaisesRegex(OSError, "injected replace failure"):
                    repository.activate("b")

            self.assertEqual(state_before, store._path.read_bytes())
            self.assertIsInstance(json.loads(store._path.read_text(encoding="utf-8")), dict)
            self.assertEqual([], list(storage_root.glob(".*.tmp")))


if __name__ == "__main__":
    unittest.main()
