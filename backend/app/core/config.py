from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Environment ---
    # "development" → uses DEV_DATABASE_URL (Neon)
    # "production"  → uses PROD_DATABASE_URL (Supabase)
    app_environment: Literal["development", "production"] = Field(
        default="development", validation_alias="APP_ENVIRONMENT"
    )

    # --- Database (explicit override, takes priority over environment selection) ---
    database_url_env: str | None = Field(default=None, validation_alias="DATABASE_URL")
    dev_database_url: str | None = Field(default=None, validation_alias="DEV_DATABASE_URL")
    prod_database_url: str | None = Field(default=None, validation_alias="PROD_DATABASE_URL")

    # Legacy individual fields (still honoured if DATABASE_URL is not set)
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "aitrailreporter"
    database_user: str = "postgres"
    database_password: str = ""

    # How close a coordinate must be to a known place before that place is considered
    # part of the coordinate's geographic context. NOT the same as each knowledge
    # type's own geographic_relevance_radius_meters (see knowledge_type_config) —
    # that governs how far an observation/guide can be for a given knowledge type,
    # this governs "is this known place nearby at all."
    geographic_context_radius_meters: int = 500

    # Upper bound on the radius_meters a caller can request from a nearby-search
    # endpoint, to prevent accidental unbounded/expensive searches.
    nearby_search_max_radius_meters: int = 50_000

    # Where uploaded voice-note audio is stored (Step 7). Relative paths are
    # resolved against the backend process's working directory. This is a local
    # filesystem directory for local development/demo only — see
    # app/services/storage/ for the storage abstraction that would be swapped for
    # an S3-compatible implementation in production.
    audio_storage_dir: str = "var/audio_uploads"

    # Generous cap for a short voice note recorded on a phone, not a general media
    # upload limit.
    max_audio_upload_size_bytes: int = 20_971_520  # 20 MiB

    # Step 16: where Explore photo uploads are stored. A SEPARATE directory from
    # audio (same storage abstraction, different root) so the two can be given
    # different operational treatment without a code change — see
    # app/services/storage/__init__.py.
    photo_storage_dir: str = "var/photo_uploads"

    # Sized for a phone photo already downscaled by the mobile client before
    # upload (see mobile/src/photo/photoPickerService.ts), not for a full
    # original-resolution capture.
    max_photo_upload_size_bytes: int = 10_485_760  # 10 MiB

    # Step 8: Sarvam AI (Saaras) transcription. The backend is the ONLY thing that
    # ever holds this key — never sent to, or read by, the mobile app. `None` (not
    # set) is a valid, expected local-dev state: the transcribe endpoint reports a
    # clean 503 rather than crashing at import time, so the rest of the API stays
    # usable without it configured.
    sarvam_api_key: str | None = None
    sarvam_transcription_model: Literal["saaras:v3", "saaras:v4"] = "saaras:v3"
    sarvam_request_timeout_seconds: float = 60.0

    # Step 9: Anthropic Claude, used for LLM structured extraction. Same pattern
    # as Sarvam above -- the backend is the ONLY thing that ever holds this key,
    # `None` is a valid local-dev state (the extract endpoint reports a clean 503
    # rather than crashing at import time).
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    anthropic_request_timeout_seconds: float = 60.0
    anthropic_max_output_tokens: int = 2048

    # --- Supabase Storage ---
    # When both are set the backend uses SupabaseMediaStorage for audio/photo
    # uploads instead of the local filesystem. Set these on Render (production)
    # via environment variables — never commit the service-role key.
    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_service_role_key: str | None = Field(
        default=None, validation_alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    # Bucket names — defaults match what the setup guide creates in the dashboard.
    supabase_audio_bucket: str = Field(default="audio-uploads", validation_alias="SUPABASE_AUDIO_BUCKET")
    supabase_photo_bucket: str = Field(default="photo-uploads", validation_alias="SUPABASE_PHOTO_BUCKET")

    # Admin dashboard (content moderation layer). This is a MINIMAL,
    # development-safe boundary, not real production authentication -- there
    # is no admin-accounts table, no session, no per-admin identity. Every
    # request to /api/v1/admin/* must present this exact token (see
    # app/core/admin_auth.py); `None` (not set) means the admin API is not
    # reachable at all rather than falling open. Never sent to, or read by,
    # the mobile app -- and never baked into the admin frontend's built JS
    # bundle, only entered by a human at its login screen (see admin/README).
    admin_api_token: str | None = None

    # Comma-separated list of allowed browser origins for the admin web app
    # (e.g. "http://localhost:5173,https://admin.example.com"). The mobile
    # app's own requests were never subject to CORS (React Native `fetch` is
    # not a browser), so this backend has never needed CORS middleware before
    # now -- see app/main.py. Deliberately NOT "*": the admin API returns
    # contributor phone numbers and other data that must not be reachable
    # from an arbitrary origin.
    admin_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Comma-separated list of allowed browser origins for the PUBLIC
    # traveller website (Next.js, default dev port 3000). Kept as its own
    # setting rather than folded into admin_cors_origins: the two surfaces
    # have very different trust levels (admin returns phone numbers; public
    # returns only pre-filtered approved content), so their allowed origins
    # should be able to diverge independently in production.
    public_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def admin_cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.admin_cors_origins.split(",") if origin.strip()]

    @property
    def public_cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.public_cors_origins.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        # 1. Explicit DATABASE_URL override always wins
        raw = self.database_url_env
        # 2. Auto-select based on APP_ENVIRONMENT
        if raw is None:
            if self.app_environment == "production":
                raw = self.prod_database_url
            else:
                raw = self.dev_database_url
        # 3. Fall back to individual host/port/name/user/password fields
        if raw is None:
            return (
                f"postgresql+psycopg://{self.database_user}:{self.database_password}"
                f"@{self.database_host}:{self.database_port}/{self.database_name}"
            )
        # Rewrite scheme so SQLAlchemy uses psycopg v3
        if raw.startswith("postgres://"):
            raw = raw.replace("postgres://", "postgresql+psycopg://", 1)
        elif raw.startswith("postgresql://") and not raw.startswith("postgresql+psycopg://"):
            raw = raw.replace("postgresql://", "postgresql+psycopg://", 1)
        return raw


settings = Settings()
