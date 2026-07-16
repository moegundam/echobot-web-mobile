from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from echobot.cli.main import build_parser
from echobot.models import LLMMessage, ToolCall
from echobot.persistence.export import (
    build_postgres_seed_export,
    validate_postgres_seed_export,
    write_postgres_seed_export,
)
from echobot.persistence.postgres_schema import (
    POSTGRES_SCHEMA_SQL,
    POSTGRES_SCHEMA_VERSION,
)
from echobot.runtime.sessions import SessionStore


class PostgresMigrationExportTests(unittest.TestCase):
    def test_schema_contains_session_centered_tables(self) -> None:
        self.assertEqual(2, POSTGRES_SCHEMA_VERSION)
        self.assertIn("begin;", POSTGRES_SCHEMA_SQL)
        self.assertIn("create table if not exists echobot_schema_migrations", POSTGRES_SCHEMA_SQL)
        self.assertIn("legacy non-tenant schema", POSTGRES_SCHEMA_SQL)
        self.assertIn("pg_get_constraintdef", POSTGRES_SCHEMA_SQL)
        self.assertIn("create table if not exists sessions", POSTGRES_SCHEMA_SQL)
        self.assertIn("create table if not exists characters", POSTGRES_SCHEMA_SQL)
        self.assertIn("create table if not exists channel_integrations", POSTGRES_SCHEMA_SQL)
        self.assertIn("create table if not exists runtime_documents", POSTGRES_SCHEMA_SQL)
        self.assertIn("create table if not exists conversation_jobs", POSTGRES_SCHEMA_SQL)
        self.assertIn("create table if not exists agent_trace_events", POSTGRES_SCHEMA_SQL)
        self.assertIn("owner_user_id", POSTGRES_SCHEMA_SQL)
        self.assertIn("primary key (owner_user_id, id)", POSTGRES_SCHEMA_SQL)
        self.assertIn(
            "foreign key (owner_user_id, session_id) references sessions(owner_user_id, id)",
            POSTGRES_SCHEMA_SQL,
        )
        self.assertNotIn("id text primary key", POSTGRES_SCHEMA_SQL)
        self.assertTrue(POSTGRES_SCHEMA_SQL.endswith("commit;"))

    def test_v2_export_is_deterministic_and_covers_all_owner_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            root = workspace / ".echobot"
            root_store = SessionStore(root / "sessions")
            session = root_store.create_session("demo")
            session.history.append(
                LLMMessage(
                    role="assistant",
                    content="done",
                    tool_calls=[
                        ToolCall(id="call-1", name="read_file", arguments='{"path":"x"}')
                    ],
                    reasoning_content="private chain state",
                    reasoning_field="reasoning",
                )
            )
            root_store.save_session(session)

            alice_root = root / "users" / "alice-111111111111"
            alice_store = SessionStore(alice_root / "sessions")
            alice_store.create_session("alice-session")
            bob_root = root / "users" / "bob-222222222222"
            bob_store = SessionStore(bob_root / "sessions")
            bob_store.create_session("bob-session")

            (root / "llm_models.json").write_text(
                json.dumps(
                    {
                        "models": {
                            "local": {
                                "model": "safe-model",
                                "max_tokens": 4096,
                                "usage": {
                                    "prompt_tokens": 12,
                                    "completion_tokens": 34,
                                },
                                "access_token": "must-also-not-export",
                                "nested": {"api_key": "must-not-export"},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "model_profile_secrets.json").write_text(
                json.dumps({"api_key": "secret-file-value"}),
                encoding="utf-8",
            )
            (root / "channels.json").write_text(
                json.dumps(
                    {
                        "discord": {
                            "enabled": True,
                            "webhook_url": "https://secret.invalid/hook",
                            "nested": {"bot_token": "channel-secret"},
                        }
                    }
                ),
                encoding="utf-8",
            )

            first = build_postgres_seed_export(workspace)
            second = build_postgres_seed_export(workspace)

            self.assertEqual(first, second)
            self.assertEqual("echobot-postgres-seed-v2", first["format"])
            self.assertEqual(
                ["default", "alice-111111111111", "bob-222222222222"],
                [scope["owner_user_id"] for scope in first["scopes"]],
            )
            default_scope = first["scopes"][0]
            exported_message = default_scope["sessions"][0]["history"][0]
            self.assertEqual("read_file", exported_message["tool_calls"][0]["name"])
            self.assertEqual("private chain state", exported_message["reasoning_content"])
            self.assertEqual("reasoning", exported_message["reasoning_field"])
            self.assertEqual("safe-model", default_scope["stores"]["llm_models"]["models"]["local"]["model"])
            self.assertEqual(4096, default_scope["stores"]["llm_models"]["models"]["local"]["max_tokens"])
            self.assertEqual(
                {"prompt_tokens": 12, "completion_tokens": 34},
                default_scope["stores"]["llm_models"]["models"]["local"]["usage"],
            )
            self.assertEqual(
                "",
                default_scope["stores"]["llm_models"]["models"]["local"]["access_token"],
            )
            self.assertTrue(
                default_scope["stores"]["llm_models"]["models"]["local"]["access_token_configured"],
            )
            self.assertEqual("", default_scope["stores"]["llm_models"]["models"]["local"]["nested"]["api_key"])
            self.assertTrue(default_scope["stores"]["llm_models"]["models"]["local"]["nested"]["api_key_configured"])
            self.assertNotIn("model_profile_secrets", default_scope["stores"])
            serialized = json.dumps(first, ensure_ascii=False)
            self.assertNotIn("must-not-export", serialized)
            self.assertNotIn("must-also-not-export", serialized)
            self.assertNotIn("secret-file-value", serialized)
            self.assertNotIn("secret.invalid", serialized)
            self.assertNotIn("channel-secret", serialized)
            self.assertEqual([], validate_postgres_seed_export(first))
            self.assertEqual(64, len(first["manifest"]["sha256"]))

    def test_export_redacts_camel_case_secrets_inside_json_strings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            storage_root = workspace / ".echobot"
            storage_root.mkdir(parents=True)
            (storage_root / "runtime_settings.json").write_text(
                json.dumps(
                    {
                        "tool_arguments": json.dumps(
                            {
                                "accessToken": "sentinel-access-value",
                                "nested": {"apiKey": "sentinel-api-value"},
                                "maxTokens": 512,
                            }
                        )
                    }
                ),
                encoding="utf-8",
            )

            payload = build_postgres_seed_export(workspace)
            serialized = json.dumps(payload, ensure_ascii=False)
            arguments = json.loads(
                payload["scopes"][0]["stores"]["runtime_settings"]["tool_arguments"]
            )

            self.assertNotIn("sentinel-access-value", serialized)
            self.assertNotIn("sentinel-api-value", serialized)
            self.assertEqual("", arguments["accessToken"])
            self.assertTrue(arguments["accessToken_configured"])
            self.assertEqual("", arguments["nested"]["apiKey"])
            self.assertTrue(arguments["nested"]["apiKey_configured"])
            self.assertEqual(512, arguments["maxTokens"])

    def test_export_redacts_double_encoded_normalized_credential_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            storage_root = workspace / ".echobot"
            storage_root.mkdir(parents=True)
            credentials = {
                "secretKey": "sentinel-secret-key",
                "awsSecretAccessKey": "sentinel-aws-secret",
                "tokenValue": "sentinel-token-value",
                "service.secret-key": "sentinel-normalized-secret",
                "provider-token-value": "sentinel-normalized-token",
            }
            (storage_root / "runtime_settings.json").write_text(
                json.dumps(
                    {
                        "tool_arguments": json.dumps(json.dumps(credentials)),
                    }
                ),
                encoding="utf-8",
            )

            payload = build_postgres_seed_export(workspace)
            encoded_arguments = payload["scopes"][0]["stores"]["runtime_settings"][
                "tool_arguments"
            ]
            arguments = json.loads(json.loads(encoded_arguments))
            serialized = json.dumps(payload, ensure_ascii=False)

            for key, secret_value in credentials.items():
                self.assertNotIn(secret_value, serialized)
                self.assertEqual("", arguments[key])
                self.assertTrue(arguments[f"{key}_configured"])

    def test_export_preserves_non_secret_token_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            storage_root = workspace / ".echobot"
            storage_root.mkdir(parents=True)
            parameters = {
                "maxToken": 256,
                "maxTokens": 512,
                "max_token": 1024,
                "tokenCount": 12,
                "tokenLimit": 2048,
                "temperature": 0.7,
                "modelName": "safe-model",
            }
            (storage_root / "runtime_settings.json").write_text(
                json.dumps({"parameters": parameters}),
                encoding="utf-8",
            )

            payload = build_postgres_seed_export(workspace)
            exported = payload["scopes"][0]["stores"]["runtime_settings"][
                "parameters"
            ]

            self.assertEqual(parameters, exported)
            self.assertFalse(
                any(key.endswith("_configured") for key in exported)
            )

    def test_export_fails_closed_at_json_string_decode_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            storage_root = workspace / ".echobot"
            storage_root.mkdir(parents=True)
            encoded = json.dumps({"secretKey": "sentinel-too-deep"})
            for _ in range(12):
                encoded = json.dumps(encoded)
            (storage_root / "runtime_settings.json").write_text(
                json.dumps({"tool_arguments": encoded}),
                encoding="utf-8",
            )

            payload = build_postgres_seed_export(workspace)

            self.assertNotIn(
                "sentinel-too-deep",
                json.dumps(payload, ensure_ascii=False),
            )

    def test_attachment_manifest_hashes_content_without_embedding_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            attachment_root = workspace / ".echobot" / "attachments"
            files = attachment_root / "files"
            metadata = attachment_root / "meta"
            files.mkdir(parents=True)
            metadata.mkdir(parents=True)
            content = b"attachment contents\n"
            (files / "file_a.txt").write_bytes(content)
            (metadata / "file_a.json").write_text(
                json.dumps(
                    {
                        "kind": "file",
                        "attachment_id": "file_a",
                        "relative_path": "files/file_a.txt",
                        "content_type": "text/plain",
                        "original_filename": "example.txt",
                        "size_bytes": len(content),
                        "sha256": "stale-metadata-hash",
                        "created_at": "2026-07-17T00:00:00+08:00",
                    }
                ),
                encoding="utf-8",
            )

            payload = build_postgres_seed_export(workspace)
            attachment = payload["scopes"][0]["attachments"][0]

            self.assertEqual("file_a", attachment["attachment_id"])
            self.assertEqual(len(content), attachment["size_bytes"])
            self.assertEqual(
                "388dd55f16b0b7ccdf7abdc7a0daea7872ef521de56ee820b4440e52c87d081b",
                attachment["sha256"],
            )
            self.assertNotIn("attachment contents", json.dumps(payload))
            self.assertEqual(1, payload["manifest"]["counts"]["attachments"])

    def test_corrupt_records_are_reported_and_block_file_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            storage_root = workspace / ".echobot"
            storage_root.mkdir(parents=True)
            (storage_root / "delivery.json").write_text("{broken", encoding="utf-8")

            payload = build_postgres_seed_export(workspace)
            errors = validate_postgres_seed_export(payload)

            self.assertTrue(any("delivery.json" in item for item in errors))
            output = workspace / "seed.json"
            with self.assertRaisesRegex(ValueError, "validation failed"):
                write_postgres_seed_export(workspace, output)
            self.assertFalse(output.exists())

    def test_seed_write_atomically_replaces_with_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            output = workspace / "exports" / "seed.json"
            output.parent.mkdir()
            output.write_text("previous seed\n", encoding="utf-8")
            output.chmod(0o644)
            real_replace = os.replace
            replace_calls: list[tuple[Path, Path]] = []

            def assert_then_replace(source: str | Path, target: str | Path) -> None:
                source_path = Path(source)
                target_path = Path(target)
                self.assertEqual("previous seed\n", output.read_text(encoding="utf-8"))
                self.assertEqual(0o600, stat.S_IMODE(source_path.stat().st_mode))
                replace_calls.append((source_path, target_path))
                real_replace(source_path, target_path)

            with mock.patch(
                "echobot.persistence.export.os.replace",
                side_effect=assert_then_replace,
            ):
                payload = write_postgres_seed_export(workspace, output)

            self.assertEqual(1, len(replace_calls))
            self.assertEqual(output, replace_calls[0][1])
            self.assertEqual(payload, json.loads(output.read_text(encoding="utf-8")))
            self.assertEqual(0o600, stat.S_IMODE(output.stat().st_mode))

    def test_seed_write_failure_preserves_previous_file_and_removes_temporary_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            output = workspace / "seed.json"
            output.write_text("previous seed\n", encoding="utf-8")

            with mock.patch(
                "echobot.persistence.export.os.replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaises(OSError):
                    write_postgres_seed_export(workspace, output)

            self.assertEqual("previous seed\n", output.read_text(encoding="utf-8"))
            self.assertEqual([], list(workspace.glob(".seed.json.*")))

    def test_validator_detects_payload_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = build_postgres_seed_export(Path(temp_dir))
            payload["notes"].append("tampered")

            self.assertTrue(
                any("digest" in item.lower() for item in validate_postgres_seed_export(payload))
            )

    def test_cli_dry_run_validates_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            output = workspace / "must-not-exist.json"
            parser = build_parser()
            args = parser.parse_args(
                [
                    "db",
                    "export",
                    "--workspace",
                    str(workspace),
                    "--output",
                    str(output),
                    "--dry-run",
                ]
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = args.handler(args)

            self.assertEqual(0, result)
            self.assertFalse(output.exists())
            self.assertIn("echobot-postgres-seed-v2", stdout.getvalue())
            self.assertIn("sha256", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
