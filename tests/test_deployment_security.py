from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from echobot.app import create_app
from echobot.app.auth import (
    AdminAccessConfig,
    DeploymentSecurityConfig,
    TrustedUserConfig,
    validate_deployment_security,
)
from echobot.runtime.bootstrap import RuntimeOptions


def test_local_profile_keeps_single_user_development_available() -> None:
    validate_deployment_security(
        DeploymentSecurityConfig(profile="local"),
        TrustedUserConfig(),
        AdminAccessConfig(),
    )


@pytest.mark.parametrize("profile", ["tunnel", "public", "production", "vps"])
def test_exposed_profiles_fail_closed_without_identity_and_admin_guards(
    profile: str,
) -> None:
    with pytest.raises(ValueError, match="requires trusted-user authentication"):
        validate_deployment_security(
            DeploymentSecurityConfig(profile=profile),
            TrustedUserConfig(),
            AdminAccessConfig(),
        )


def test_exposed_profile_rejects_wildcard_admin_access() -> None:
    with pytest.raises(ValueError, match="explicit admin allowlist"):
        validate_deployment_security(
            DeploymentSecurityConfig(profile="tunnel"),
            TrustedUserConfig(enabled=True, required=True),
            AdminAccessConfig(allowlist=frozenset({"*"}), required=True),
        )


def test_exposed_profile_accepts_required_identity_and_named_admin() -> None:
    validate_deployment_security(
        DeploymentSecurityConfig(profile="tunnel"),
        TrustedUserConfig(enabled=True, required=True),
        AdminAccessConfig(
            allowlist=frozenset({"admin@example.test"}),
            required=True,
        ),
    )


def test_create_app_loads_deployment_security_from_runtime_env_file() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        (workspace / ".env").write_text(
            "\n".join(
                [
                    "ECHOBOT_DEPLOYMENT_PROFILE=tunnel",
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED=true",
                    "ECHOBOT_ADMIN_ALLOWLIST=admin@example.test",
                    "ECHOBOT_ADMIN_REQUIRED=true",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {}, clear=True):
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    env_file=".env",
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
            )

        assert app.state.deployment_security_config.profile == "tunnel"
        assert app.state.trusted_user_config.required is True
        assert app.state.admin_access_config.is_admin("admin@example.test") is True


def test_create_app_rejects_incomplete_public_env_file() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        (workspace / ".env").write_text(
            "ECHOBOT_DEPLOYMENT_PROFILE=public\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="requires trusted-user authentication"):
                create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        env_file=".env",
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                )
