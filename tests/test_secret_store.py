from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from echobot.secrets import (
    EnvironmentSecretStore,
    LocalJsonSecretStore,
    SecretConfigurationError,
    SecretPermissionError,
    SecretStore,
    SecretStoreError,
)


class EnvironmentSecretStoreTests(unittest.TestCase):
    def test_direct_environment_secret_is_redacted_from_repr(self) -> None:
        plaintext = "direct-secret-value"
        store = EnvironmentSecretStore({"SERVICE_TOKEN": plaintext})

        resolved = store.get("SERVICE_TOKEN")

        self.assertIsInstance(store, SecretStore)
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(plaintext, resolved.value)
        self.assertTrue(resolved.metadata.configured)
        self.assertEqual("environment", resolved.metadata.source)
        self.assertIsNone(resolved.metadata.version)
        self.assertNotIn(plaintext, repr(resolved))

    def test_missing_environment_secret_has_unconfigured_metadata(self) -> None:
        store = EnvironmentSecretStore({})

        self.assertIsNone(store.get("SERVICE_TOKEN"))
        metadata = store.metadata("SERVICE_TOKEN")

        self.assertFalse(metadata.configured)
        self.assertIsNone(metadata.source)
        self.assertIsNone(metadata.version)
        self.assertFalse(hasattr(metadata, "value"))

    def test_environment_and_file_sources_are_rejected_as_ambiguous(self) -> None:
        plaintext = "direct-secret-value"
        secret_path = "/tmp/file-secret-value"
        store = EnvironmentSecretStore(
            {
                "SERVICE_TOKEN": plaintext,
                "SERVICE_TOKEN_FILE": secret_path,
            }
        )

        with self.assertRaises(SecretConfigurationError) as raised:
            store.get("SERVICE_TOKEN")

        message = str(raised.exception)
        self.assertNotIn(plaintext, message)
        self.assertNotIn(secret_path, message)

    def test_ambiguity_uses_presence_even_when_direct_value_is_empty(
        self,
    ) -> None:
        store = EnvironmentSecretStore(
            {
                "SERVICE_TOKEN": "",
                "SERVICE_TOKEN_FILE": "/tmp/secret",
            }
        )

        with self.assertRaises(SecretConfigurationError):
            store.get("SERVICE_TOKEN")

    def test_file_source_reads_strict_utf8_with_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / "service-token"
            plaintext = "token-\u96ea"
            secret_path.write_text(plaintext, encoding="utf-8")
            store = EnvironmentSecretStore(
                {"SERVICE_TOKEN_FILE": str(secret_path)}
            )

            resolved = store.get("SERVICE_TOKEN")

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(plaintext, resolved.value)
        self.assertEqual("environment_file", resolved.metadata.source)
        self.assertIsNotNone(resolved.metadata.version)
        self.assertNotIn(plaintext, repr(resolved))

    def test_file_source_allows_mounted_secret_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / "mounted-token"
            secret_link = Path(temp_dir) / "service-token"
            plaintext = "mounted-secret-value"
            secret_path.write_text(plaintext, encoding="utf-8")
            secret_link.symlink_to(secret_path)
            store = EnvironmentSecretStore(
                {"SERVICE_TOKEN_FILE": str(secret_link)}
            )

            resolved = store.get("SERVICE_TOKEN")

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(plaintext, resolved.value)

    def test_file_source_rejects_oversized_content_without_leaking_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / "service-token"
            plaintext = "oversized-secret-value"
            secret_path.write_bytes(plaintext.encode("utf-8"))
            store = EnvironmentSecretStore(
                {"SERVICE_TOKEN_FILE": str(secret_path)},
                max_secret_bytes=8,
            )

            with self.assertRaises(SecretStoreError) as raised:
                store.get("SERVICE_TOKEN")

        self.assertNotIn(plaintext, str(raised.exception))

    def test_file_source_rejects_invalid_utf8_without_leaking_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / "service-token"
            secret_path.write_bytes(b"secret-prefix-\xff-secret-suffix")
            store = EnvironmentSecretStore(
                {"SERVICE_TOKEN_FILE": str(secret_path)}
            )

            with self.assertRaises(SecretStoreError) as raised:
                store.get("SERVICE_TOKEN")

        self.assertNotIn("secret-prefix", str(raised.exception))
        self.assertNotIn("secret-suffix", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)

    def test_invalid_environment_text_has_no_leaking_exception_context(self) -> None:
        plaintext = "secret-prefix-\ud800-secret-suffix"
        store = EnvironmentSecretStore({"SERVICE_TOKEN": plaintext})

        with self.assertRaises(SecretConfigurationError) as raised:
            store.get("SERVICE_TOKEN")

        self.assertNotIn("secret-prefix", str(raised.exception))
        self.assertNotIn("secret-suffix", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)

    def test_explicit_empty_secret_fails_closed(self) -> None:
        store = EnvironmentSecretStore({"SERVICE_TOKEN": ""})

        with self.assertRaises(SecretConfigurationError):
            store.get("SERVICE_TOKEN")


class LocalJsonSecretStoreTests(unittest.TestCase):
    def test_replace_all_writes_one_atomic_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "secrets.json"
            store = LocalJsonSecretStore(store_path)
            store.set("stale-token", "stale-secret")

            metadata = store.replace_all(
                {
                    "telegram.bot_token": "telegram-secret",
                    "discord.bot_token": "discord-secret",
                }
            )

            self.assertTrue(metadata.configured)
            self.assertEqual("local_json", metadata.source)
            self.assertIsNotNone(metadata.version)
            self.assertEqual(
                {
                    "discord.bot_token": "discord-secret",
                    "telegram.bot_token": "telegram-secret",
                },
                json.loads(store_path.read_text(encoding="utf-8")),
            )
            self.assertEqual(0o600, stat.S_IMODE(store_path.stat().st_mode))
            self.assertIsNone(store.get("stale-token"))

    def test_replace_all_rejects_invalid_snapshot_without_partial_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "secrets.json"
            store = LocalJsonSecretStore(store_path)
            store.set("service-token", "original-secret")

            with self.assertRaises(SecretConfigurationError):
                store.replace_all(
                    {
                        "service-token": "replacement-secret",
                        "invalid": "",
                    }
                )

            resolved = store.get("service-token")
            self.assertIsNotNone(resolved)
            assert resolved is not None
            self.assertEqual("original-secret", resolved.value)

    def test_set_get_and_delete_use_flat_json_with_restricted_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "secrets.json"
            store = LocalJsonSecretStore(store_path)

            first_metadata = store.set("service-token", "first-secret")
            first_mode = stat.S_IMODE(store_path.stat().st_mode)
            raw_payload = json.loads(store_path.read_text(encoding="utf-8"))
            resolved = store.get("service-token")

            self.assertEqual({"service-token": "first-secret"}, raw_payload)
            self.assertEqual(0o600, first_mode)
            self.assertTrue(first_metadata.configured)
            self.assertEqual("local_json", first_metadata.source)
            self.assertIsNotNone(first_metadata.version)
            self.assertIsNotNone(resolved)
            assert resolved is not None
            self.assertEqual("first-secret", resolved.value)
            self.assertEqual(first_metadata, resolved.metadata)
            self.assertNotIn("first-secret", repr(resolved))

            second_metadata = store.set("service-token", "other-secret")
            self.assertNotEqual(first_metadata.version, second_metadata.version)

            deleted_metadata = store.delete("service-token")
            self.assertFalse(deleted_metadata.configured)
            self.assertIsNone(deleted_metadata.version)
            self.assertIsNone(store.get("service-token"))

    def test_reads_existing_flat_json_compatibility_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "secrets.json"
            store_path.write_text(
                json.dumps({"existing-token": "existing-secret"}),
                encoding="utf-8",
            )
            store_path.chmod(0o600)

            resolved = LocalJsonSecretStore(store_path).get("existing-token")

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual("existing-secret", resolved.value)
        self.assertTrue(resolved.metadata.configured)
        self.assertIsNotNone(resolved.metadata.version)

    def test_refuses_existing_file_with_group_or_other_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "secrets.json"
            plaintext = "permission-secret"
            store_path.write_text(
                json.dumps({"service-token": plaintext}),
                encoding="utf-8",
            )
            store_path.chmod(0o644)

            with self.assertRaises(SecretPermissionError) as raised:
                LocalJsonSecretStore(store_path).get("service-token")

        self.assertNotIn(plaintext, str(raised.exception))

    def test_refuses_symbolic_link_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "target.json"
            store_path = Path(temp_dir) / "secrets.json"
            plaintext = "linked-secret-value"
            target_path.write_text(
                json.dumps({"service-token": plaintext}),
                encoding="utf-8",
            )
            target_path.chmod(0o600)
            store_path.symlink_to(target_path)

            with self.assertRaises(SecretPermissionError) as raised:
                LocalJsonSecretStore(store_path).get("service-token")

        self.assertNotIn(plaintext, str(raised.exception))
        self.assertNotIn(str(target_path), str(raised.exception))

    def test_rejects_invalid_json_value_without_leaking_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "secrets.json"
            plaintext = "nested-secret-value"
            store_path.write_text(
                json.dumps({"service-token": {"value": plaintext}}),
                encoding="utf-8",
            )
            store_path.chmod(0o600)

            with self.assertRaises(SecretStoreError) as raised:
                LocalJsonSecretStore(store_path).get("service-token")

        self.assertNotIn(plaintext, str(raised.exception))

    def test_rejects_malformed_json_without_leaking_parser_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "secrets.json"
            plaintext = "malformed-json-secret"
            store_path.write_text(
                '{"service-token":"' + plaintext + '"',
                encoding="utf-8",
            )
            store_path.chmod(0o600)

            with self.assertRaises(SecretStoreError) as raised:
                LocalJsonSecretStore(store_path).get("service-token")

        self.assertNotIn(plaintext, str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)

    def test_rejects_oversized_json_without_leaking_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "secrets.json"
            plaintext = "oversized-json-secret"
            store_path.write_text(
                json.dumps({"service-token": plaintext}),
                encoding="utf-8",
            )
            store_path.chmod(0o600)
            store = LocalJsonSecretStore(store_path, max_file_bytes=16)

            with self.assertRaises(SecretStoreError) as raised:
                store.get("service-token")

        self.assertNotIn(plaintext, str(raised.exception))

    def test_set_rejects_empty_secret_without_writing_plaintext(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "secrets.json"
            store = LocalJsonSecretStore(store_path)

            with self.assertRaises(SecretConfigurationError):
                store.set("service-token", "")

            self.assertFalse(store_path.exists())


if __name__ == "__main__":
    unittest.main()
