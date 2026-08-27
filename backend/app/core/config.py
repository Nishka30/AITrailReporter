from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url_env: str | None = Field(default=None, validation_alias="DATABASE_URL")
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

    @property
    def database_url(self) -> str:
        if self.database_url_env:
            url = self.database_url_env
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg://", 1)
            elif url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url
        return (
            f"postgresql+psycopg://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


settings = Settings()
