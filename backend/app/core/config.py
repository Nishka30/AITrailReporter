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

    # Step 18: popular-question web research. How long a successful research
    # run stays valid before a refresh is allowed. Popular questions about a
    # place ("is it safe to cross?") change slowly, and every refresh costs a
    # real web search, so this is deliberately generous -- see
    # app/services/place_questions.py, which is the ONLY thing that reads it.
    place_question_refresh_days: int = 30

    # Upper bound on how many popular questions are kept per place. The
    # research prompt asks for "5-6"; this is the hard cap applied
    # server-side afterwards, so a model returning more can never flood a
    # place's list.
    place_question_max_count: int = 6

    # The budget for ONE COMPLETE research run for a place: reverse geocode,
    # up to perplexity_max_queries_per_place web searches, then one generation
    # call. Not a per-request timeout -- each provider has its own
    # (perplexity_request_timeout_seconds, anthropic_request_timeout_seconds).
    # This is the whole-run bound, and its only consumer is
    # place_questions.is_abandoned, which uses it to decide when a run that
    # claimed a place and then died can safely be reclaimed.
    #
    # Set generously. Reclaiming too early would let two runs research the same
    # place and pay twice; reclaiming late only delays a refresh, and the
    # previously researched questions stay served throughout.
    place_question_research_timeout_seconds: float = 300.0

    # --- POI discovery (app/services/poi_discovery.py) --------------------
    # Discovery is what fills the `locations` table from web research, so the
    # system can be place-specific somewhere nobody curated by hand.
    #
    # Grid cell size for caching a discovery run. 0.01 deg is ~1.1km of
    # latitude. Small enough that one run's results are genuinely "around
    # here", large enough that a stationary phone's GPS jitter never crosses a
    # cell boundary and re-triggers a paid web search.
    poi_discovery_cell_degrees: float = 0.01
    # How far around the cell centre research is asked to look.
    poi_discovery_search_radius_meters: int = 1500
    # A discovered place whose coordinates fall further than this from the cell
    # centre is REJECTED, not clamped. This is the primary defence against
    # invented coordinates: a hallucinated lat/lon is rarely near the query
    # point by luck. Deliberately a little wider than the search radius so a
    # genuine place near the edge isn't discarded for rounding.
    poi_discovery_accept_radius_meters: int = 2500
    # Two places closer together than this are treated as the same physical
    # thing. Dedup is geographic rather than by name because the same bridge
    # appears under several names across sources.
    poi_discovery_dedup_radius_meters: int = 60
    # Hard cap on Locations created by ONE discovery run. Blast-radius control,
    # the same reasoning as MAX_NEW_TYPES_PER_EXTRACTION: structure can be
    # validated, genuine local significance cannot, so one over-eager run can
    # add at most this many anchors.
    poi_discovery_max_places: int = 8
    # How long a successful run stays valid. Named places appear and close
    # slowly, and every refresh costs a request to a free, donated service.
    poi_discovery_refresh_days: int = 60
    # How many OSM candidates to fetch before the selection step filters them.
    # Comfortably more than poi_discovery_max_places, so selection has real
    # choices to make rather than rubber-stamping whatever came back first.
    poi_discovery_candidate_limit: int = 40

    # --- OpenStreetMap ----------------------------------------------------
    # Overpass supplies the FACTS for discovery: what named places exist and
    # exactly where. Coordinates never come from a language model, which is
    # what makes an invented landmark structurally impossible rather than
    # merely discouraged (see services/poi_discovery_research/osm_provider.py).
    #
    # Free and keyless, but a donated service: this project sends one request
    # per grid cell and caches the result for poi_discovery_refresh_days.
    # Overridable so a self-hosted or commercial Overpass instance can be used
    # without a code change.
    osm_overpass_url: str = "https://overpass-api.de/api/interpreter"
    osm_request_timeout_seconds: float = 60.0
    # Reverse geocoding, used only to name the locality a place sits in
    # ("Koramangala, Bengaluru"). That name matters more than it looks: web
    # research for "Ganesh Temple" alone is hopeless, while the same query with
    # its locality attached returns the right temple. One call per place, then
    # stored on the Location forever.
    osm_nominatim_url: str = "https://nominatim.openstreetmap.org/reverse"
    # Forward geocoding ("Kedarnath" -> coordinates), for the place-autocomplete
    # feature. A separate URL/setting from the reverse endpoint above because
    # Nominatim exposes them as distinct paths and a self-hosted deployment
    # could reasonably run one without the other.
    osm_nominatim_search_url: str = "https://nominatim.openstreetmap.org/search"

    # How far apart (in hours) a GuideLocation sample may be from a
    # submission's occurred_at and still be trusted as that submission's
    # location. This is the ENTIRE safeguard against the failure this feature
    # exists to prevent: a photo taken weeks ago being assigned wherever the
    # guide happened to be standing today. Deliberately tight -- a guide moves
    # kilometres in a few hours, so "close in time" is the only honest
    # definition of "close" available here (there is no independent distance
    # signal to cross-check against). Beyond this window, location stays
    # "unknown" rather than guessing from a stale or future sample; see
    # app/services/extractions.py:_resolve_observation_coordinates.
    historical_location_max_gap_hours: float = 6.0

    # --- Perplexity (web research) ---------------------------------------
    # The WEB RESEARCH layer: given a place this system already knows exists
    # (from OSM or manual curation), Perplexity finds what people actually say
    # about it, with citations. Backend-only, exactly like the Anthropic and
    # Sarvam keys -- never sent to, or read by, the mobile app. `None` is a
    # valid local-dev state: research reports a clean failure and the app keeps
    # serving whatever questions already exist.
    #
    # NOTE ON SCOPE: Perplexity is NOT used to discover what is near a
    # coordinate. It cannot -- see app/services/research/perplexity_provider.py
    # for the measured reason. Discovery is OSM's job; this is research about a
    # named entity.
    perplexity_api_key: str | None = None
    perplexity_api_url: str = "https://api.perplexity.ai/chat/completions"
    # 'sonar' costs roughly half of 'sonar-pro' per request and, in side-by-side
    # runs on the same places, returned the same specific facts. Overridable if
    # that stops being true.
    perplexity_model: str = "sonar"
    perplexity_request_timeout_seconds: float = 90.0
    # Hard cap on paid searches per place per refresh cycle. Deliberately small:
    # the second query only runs when the first actually found something (see
    # place_question_research/research_plan.py), so a place nobody has written
    # about costs one request, not a fixed budget.
    perplexity_max_queries_per_place: int = 2
    # Research text is stored for provenance, not archived wholesale. Enough to
    # audit why a question was asked; not a copy of the web.
    place_research_max_summary_chars: int = 4000

    # Step 18: reward points -> money. `10` means 10 points = 1.00 of
    # reward_currency_code. Configured here rather than in the mobile app so
    # the rate can change without an app release -- the app only ever DISPLAYS
    # the conversion the backend reports (see app/api/routes/rewards.py).
    #
    # NOTE: no payout/redemption mechanism exists in this system. This value
    # drives an "approximate value" display only; nothing here moves money.
    reward_points_per_currency_unit: int = 10
    reward_currency_code: str = "USD"
    reward_currency_symbol: str = "$"

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
