from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Backblaze B2 (required at runtime)
    b2_endpoint: str = ""
    b2_region: str = ""
    b2_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket_name: str = ""
    b2_public_url: str = ""

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

    # Default redaction layers applied on /record when the user hasn't
    # explicitly customized them. Comma-separated subset of
    # {pii, secrets, glossary}.
    redaction_default_modes: str = "pii,secrets,glossary"

    # Storage default. When true (v1 default — convenient for dev testing
    # so the original audio + transcript can be replayed and compared
    # against the redacted variant), /record writes raw audio AND the
    # unredacted transcript alongside the redacted bundle. When false,
    # only the redacted transcript + manifest + audit trail are written
    # (the privacy default — flip this in production).
    session_store_originals_default: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

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
