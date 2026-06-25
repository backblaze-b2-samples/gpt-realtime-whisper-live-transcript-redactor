from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.settings import Settings
from app.repo import b2_client

REPO_ROOT = Path(__file__).resolve().parents[3]
B2_ENV_KEYS = (
    "B2_APPLICATION_KEY_ID",
    "B2_KEY_ID",
    "B2_APPLICATION_KEY",
    "B2_BUCKET_NAME",
    "B2_REGION",
    "B2_PUBLIC_URL_BASE",
    "B2_PUBLIC_URL",
    "B2_ENDPOINT",
)
LEGACY_ENV_EXAMPLE_ALIASES = ("B2_KEY_ID", "B2_ENDPOINT", "B2_PUBLIC_URL=")


def _clear_b2_env(monkeypatch):
    for key in B2_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_settings_accept_standard_b2_env_names(monkeypatch):
    _clear_b2_env(monkeypatch)
    monkeypatch.setenv("B2_APPLICATION_KEY_ID", "sample-key-id")
    monkeypatch.setenv("B2_APPLICATION_KEY", "sample-key")
    monkeypatch.setenv("B2_BUCKET_NAME", "sample-bucket")
    monkeypatch.setenv("B2_REGION", "us-west-004")
    monkeypatch.setenv("B2_PUBLIC_URL_BASE", "https://files.example.com")

    settings = Settings(_env_file=None)

    assert settings.b2_application_key_id == "sample-key-id"
    assert settings.b2_application_key == "sample-key"
    assert settings.b2_bucket_name == "sample-bucket"
    assert settings.b2_s3_endpoint_url == "https://s3.us-west-004.backblazeb2.com"
    assert settings.b2_public_url_base == "https://files.example.com"


def test_settings_accept_legacy_b2_env_names(monkeypatch):
    _clear_b2_env(monkeypatch)
    monkeypatch.setenv("B2_KEY_ID", "legacy-key-id")
    monkeypatch.setenv("B2_APPLICATION_KEY", "legacy-key")
    monkeypatch.setenv("B2_BUCKET_NAME", "legacy-bucket")
    monkeypatch.setenv("B2_REGION", "us-east-005")
    monkeypatch.setenv("B2_ENDPOINT", "https://legacy.example.invalid")
    monkeypatch.setenv("B2_PUBLIC_URL", "https://legacy-files.example.com")

    settings = Settings(_env_file=None)

    assert settings.b2_application_key_id == "legacy-key-id"
    assert settings.b2_application_key == "legacy-key"
    assert settings.b2_bucket_name == "legacy-bucket"
    assert settings.b2_s3_endpoint_url == "https://s3.us-east-005.backblazeb2.com"
    assert settings.b2_public_url_base == "https://legacy-files.example.com"


def test_settings_prefer_standard_names_when_both_present(tmp_path, monkeypatch):
    _clear_b2_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "B2_APPLICATION_KEY_ID=standard-key-id",
                "B2_KEY_ID=legacy-key-id",
                "B2_APPLICATION_KEY=sample-key",
                "B2_BUCKET_NAME=sample-bucket",
                "B2_REGION=eu-central-003",
                "B2_ENDPOINT=https://legacy.example.invalid",
                "B2_PUBLIC_URL_BASE=https://standard-files.example.com",
                "B2_PUBLIC_URL=https://legacy-files.example.com",
            ]
        )
    )

    settings = Settings(_env_file=env_file)

    assert settings.b2_application_key_id == "standard-key-id"
    assert settings.b2_s3_endpoint_url == "https://s3.eu-central-003.backblazeb2.com"
    assert settings.b2_public_url_base == "https://standard-files.example.com"


def test_settings_fall_back_when_standard_names_are_blank(tmp_path, monkeypatch):
    _clear_b2_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "B2_APPLICATION_KEY_ID=",
                "B2_KEY_ID=legacy-key-id",
                "B2_APPLICATION_KEY=sample-key",
                "B2_BUCKET_NAME=sample-bucket",
                "B2_REGION=us-west-004",
                "B2_PUBLIC_URL_BASE=",
                "B2_PUBLIC_URL=https://legacy-files.example.com",
            ]
        )
    )

    settings = Settings(_env_file=env_file)

    assert settings.b2_application_key_id == "legacy-key-id"
    assert settings.b2_public_url_base == "https://legacy-files.example.com"


def test_env_example_omits_legacy_b2_aliases():
    env_example = (REPO_ROOT / ".env.example").read_text()

    assert "B2_APPLICATION_KEY_ID=" in env_example
    assert "B2_PUBLIC_URL_BASE" in env_example
    for legacy_alias in LEGACY_ENV_EXAMPLE_ALIASES:
        assert legacy_alias not in env_example


@pytest.mark.parametrize(
    "region",
    [
        "attacker.example/leak",
        "attacker.example/#",
        "attacker.example?x=",
        "attacker.example/@x",
        "us-west-004@attacker.example",
        "us-west-004:443",
        " us-west-004",
        "us-west-004 ",
        "us/west/004",
        "us-west-004#",
        "us-west-004?",
        "us-west-004@",
    ],
)
def test_settings_reject_unsafe_b2_region(region, monkeypatch):
    _clear_b2_env(monkeypatch)
    monkeypatch.setenv("B2_REGION", region)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_b2_region_prevents_s3_client_creation(monkeypatch):
    called = False

    def fake_client(*_args, **_kwargs):
        nonlocal called
        called = True
        return object()

    _clear_b2_env(monkeypatch)
    monkeypatch.setenv("B2_REGION", "attacker.example/leak")
    monkeypatch.setattr(b2_client.boto3, "client", fake_client)
    b2_client.get_s3_client.cache_clear()

    try:
        with pytest.raises(ValidationError):
            Settings(_env_file=None)
    finally:
        b2_client.get_s3_client.cache_clear()

    assert called is False


def test_s3_client_uses_standard_key_id_and_user_agent(monkeypatch):
    captured: dict = {}

    def fake_client(service_name: str, **kwargs):
        captured["service_name"] = service_name
        captured["kwargs"] = kwargs
        return object()

    b2_client.get_s3_client.cache_clear()
    monkeypatch.setattr(b2_client.settings, "b2_region", "us-west-004")
    monkeypatch.setattr(
        b2_client.settings,
        "b2_application_key_id",
        "sample-key-id",
    )
    monkeypatch.setattr(b2_client.settings, "b2_application_key", "sample-key")
    monkeypatch.setattr(b2_client.boto3, "client", fake_client)

    try:
        b2_client.get_s3_client()
    finally:
        b2_client.get_s3_client.cache_clear()

    kwargs = captured["kwargs"]
    assert captured["service_name"] == "s3"
    assert kwargs["endpoint_url"] == "https://s3.us-west-004.backblazeb2.com"
    assert kwargs["aws_access_key_id"] == "sample-key-id"
    assert kwargs["aws_secret_access_key"] == "sample-key"
    assert "(backblaze-b2-samples)" in kwargs["config"].user_agent_extra
