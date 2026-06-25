import re

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Keep in sync with scripts/doctor.mjs so preflight and runtime validation agree.
B2_REGION_PATTERN = re.compile(r"^[a-z]{2}(?:-[a-z]+)+-\d{3}$")
B2_REGION_PLACEHOLDER = "your_b2_region"
B2_TRIMMED_FIELDS = (
    "b2_application_key_id",
    "b2_key_id",
    "b2_application_key",
    "b2_bucket_name",
    "b2_public_url_base",
    "b2_public_url",
    "b2_endpoint",
)


def _has_value(value: str) -> bool:
    return bool(value and value.strip())


def _clean_value(value: str) -> str:
    return value.strip() if value else ""


class Settings(BaseSettings):
    # Backblaze B2 (required at runtime)
    b2_region: str = ""
    b2_application_key_id: str = ""
    b2_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket_name: str = ""
    b2_public_url_base: str = ""
    b2_public_url: str = ""
    b2_endpoint: str = ""

    api_port: int = 8000
    # Explicit allowlist by default — covers Next on :3000 and the
    # fallback :3001 it picks if 3000 is busy. Production deploys should
    # override with the exact frontend origin.
    api_cors_origins: str = "http://localhost:3000,http://localhost:3001"
    # Optional dev-only escape hatch: a regex that matches additional
    # allowed origins. Empty by default — set this to e.g.
    # `^http://localhost:\d+$` to accept any localhost port without
    # listing each one. NEVER ship this to production.
    api_cors_origin_regex: str = ""

    # Upload limits
    max_file_size: int = 100 * 1024 * 1024  # 100MB

    # Small durable counters (downloads, etc). Point at a persistent
    # volume in production if you care about surviving restarts.
    download_count_file: str = "data/download_count.json"

    # OpenAI Realtime API — drives live transcription + the realtime
    # health probe on `/health`. The API key is required for /record to
    # function; an empty value disables realtime features but the rest
    # of the sample (Files explorer, Sessions library) still works.
    openai_api_key: str = ""
    openai_realtime_model: str = "gpt-realtime-whisper"
    openai_realtime_url: str = "wss://api.openai.com/v1/realtime"
    # REST base for the chat-completions call that powers the LLM PII
    # redaction layer (see below). Same key as realtime.
    openai_api_base: str = "https://api.openai.com/v1"

    # Default redaction layers applied on /record when the user hasn't
    # explicitly customized them. Comma-separated subset of
    # {pii, secrets, glossary}.
    redaction_default_modes: str = "pii,secrets,glossary"

    # The `pii` layer is LLM-backed, not regex. Spoken transcripts render
    # PII as natural language — names, "john at example dot com",
    # spelled-out card numbers — which deterministic patterns never match,
    # so PII extraction is delegated to a small chat model. `secrets` and
    # `glossary` remain deterministic regex layers (see
    # service/redaction_detectors.py). Set the model + a hard per-segment
    # timeout so a slow upstream can never block session finalize.
    redaction_pii_model: str = "gpt-4o-mini"
    redaction_pii_timeout_s: float = 15.0

    # Storage default. When true (v1 default — convenient for dev testing
    # so the original audio + transcript can be replayed and compared
    # against the redacted variant), /record writes raw audio AND the
    # unredacted transcript alongside the redacted bundle. When false,
    # only the redacted transcript + manifest + audit trail are written
    # (the privacy default — flip this in production).
    session_store_originals_default: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("b2_region")
    @classmethod
    def validate_b2_region(cls, value: str) -> str:
        if not value or value == B2_REGION_PLACEHOLDER:
            return value
        if not B2_REGION_PATTERN.fullmatch(value):
            raise ValueError(
                "B2_REGION must be a Backblaze region token such as us-west-004"
            )
        return value

    @model_validator(mode="after")
    def apply_legacy_b2_fallbacks(self) -> "Settings":
        for field_name in B2_TRIMMED_FIELDS:
            setattr(self, field_name, _clean_value(getattr(self, field_name)))
        if not _has_value(self.b2_application_key_id) and _has_value(self.b2_key_id):
            self.b2_application_key_id = self.b2_key_id
        if not _has_value(self.b2_public_url_base) and _has_value(self.b2_public_url):
            self.b2_public_url_base = self.b2_public_url
        return self

    @property
    def b2_s3_endpoint_url(self) -> str:
        if not self.b2_region:
            return ""
        return f"https://s3.{self.b2_region}.backblazeb2.com"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",")]

    @property
    def redaction_default_mode_list(self) -> list[str]:
        return [
            m.strip()
            for m in self.redaction_default_modes.split(",")
            if m.strip()
        ]


settings = Settings()
