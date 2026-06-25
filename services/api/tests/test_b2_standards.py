from pathlib import Path

from app.config.settings import Settings
from app.repo import b2_client

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_settings_use_standard_b2_env_names(monkeypatch):
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


def test_env_example_omits_legacy_b2_aliases():
    env_example = (REPO_ROOT / ".env.example").read_text()
    legacy_key_id = "B2_" + "KEY_ID"
    legacy_endpoint = "B2_" + "ENDPOINT"
    legacy_public_url = "B2_" + "PUBLIC_URL="

    assert "B2_APPLICATION_KEY_ID=" in env_example
    assert "B2_PUBLIC_URL_BASE" in env_example
    assert legacy_key_id not in env_example
    assert legacy_endpoint not in env_example
    assert legacy_public_url not in env_example


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
