# AI Trail Reporter — Comprehensive Database Reference & Schema README

This document provides a comprehensive, exhaustive reference for all **23 tables** and **275 columns** in the local PostgreSQL database (`postgresql://postgres:***@localhost:5432/postgres`), as configured in `backend/.env`.

---

## 1. Architectural System Overview

The database is built on top of **PostgreSQL + PostGIS + pg_trgm** and is organized around nine decoupled lifecycle pipelines plus shared infrastructure:

1. **Guide Identity & Live GPS Tracking**: Guides register (`guides`) and stream GPS location samples (`guide_locations`).
2. **Offline-First Submissions & Media**: Field reports (`submissions`) capture text, voice, or photos with extensive timestamp and geospatial provenance (`photo_exif`, `gps_live`, `historical_inferred`, etc.).
3. **Audio Transcription Lifecycle**: Asynchronous speech-to-text pipeline (`transcriptions`) driven by Sarvam AI.
4. **LLM Structured Extraction Lifecycle**: Entity and condition extraction pipeline (`extractions`) driven by Anthropic Claude.
5. **Knowledge & Moderation Layer**: Verified extracted facts (`observations`) categorized by knowledge policy (`knowledge_type_config`) and moderated by admins (`observation_moderation`).
6. **Locations, POIs & Web Research**: Spatial POIs (`locations`), focal exploration anchors (`curated_hubs`), grid-cell discovery (`poi_discovery`), and web grounding (`place_question_research`, `place_research_findings`, `place_questions`).
7. **Location Classification**: A controlled category vocabulary (`location_categories`) applied many-to-one onto places (`location_category_assignments`), so a Location can be several things at once — Nature *and* Wildlife *and* Adventure — each with its own per-place relevance. Additive to `locations.category`/`subcategory`, which are unchanged.
8. **Knowledge Gap & Question Dispatching**: Data-gap questions (`questions`) assigned to guides on the trail (`question_assignments`) and answered (`question_answers`).
9. **Reward Ledger & Gamification**: Append-only point reward ledger (`reward_ledger`) governed by configurable point values (`reward_rules`).
10. **Infrastructure**: Database versioning (`alembic_version`) and PostGIS projection metadata (`spatial_ref_sys`).

---

## 2. Table-by-Table & Column-by-Column Reference

### 1. `guides`
Represents registered mountain guides, trek leaders, or field contributors.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key identifier for the guide. |
| `name` | `character varying(255)` | **No** | None | - | Full name or callsign of the guide. |
| `phone_number` | `character varying(32)` | Yes | None | - | Contact phone number for authentication or SMS dispatching. |
| `client_guide_id` | `character varying(255)` | Yes | None | **UNIQUE** | Client-generated UUID for offline-first creation idempotency. Prevents duplicate guide records on retries. |
| `is_active` | `boolean` | **No** | `true` | - | Flag indicating whether the guide is actively taking treks and eligible to receive questions. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Server timestamp when the guide record was first created. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Server timestamp when the guide record was last modified. |

---

### 2. `guide_locations`
Historical GPS breadcrumbs recorded for guides during treks. This table is append-only.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the location ping. |
| `guide_id` | `uuid` | **No** | None | **FK** &rarr; `guides.id` (CASCADE) | Reference to the guide who broadcast this location ping. |
| `client_location_id` | `character varying(255)` | Yes | None | **UNIQUE** | Client-generated UUID ensuring duplicate sync batches don't insert duplicate GPS points. |
| `latitude` | `numeric(9,6)` | **No** | None | - | WGS-84 latitude coordinate of the guide. |
| `longitude` | `numeric(9,6)` | **No** | None | - | WGS-84 longitude coordinate of the guide. |
| `geog` | `geography(POINT, 4326)`| **No** | None | - | PostGIS geography point in SRID 4326 used for spatial indexing and radius queries (`ST_DWithin`). |
| `accuracy_meters` | `double precision` | Yes | None | - | GPS sensor horizontal accuracy radius in meters reported by mobile device hardware. |
| `recorded_at` | `timestamp with time zone` | **No** | None | - | Exact device hardware clock timestamp when the GPS satellite fix was acquired. |
| `received_at` | `timestamp with time zone` | **No** | `now()` | - | Server timestamp when the sync batch actually reached the API. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Database row insertion timestamp. |

---

### 3. `submissions`
Raw incoming reports from guides (voice recordings, camera photos, or notes) before structured extraction.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key identifier for the submission. |
| `guide_id` | `uuid` | **No** | None | **FK** &rarr; `guides.id` (CASCADE) | The guide who submitted this field report. |
| `source_question_id` | `uuid` | Yes | None | **FK** &rarr; `questions.id` (SET NULL) | If this submission answers a knowledge-gap Question, traces back to that question. |
| `source_place_question_id` | `uuid` | Yes | None | **FK** &rarr; `place_questions.id` (SET NULL) | If this submission answers a researched place prompt, traces back to that place question. |
| `client_submission_id`| `character varying(255)` | Yes | None | **UNIQUE** | Mobile-generated UUID ensuring submission creation is strictly idempotent across network retries. |
| `latitude` | `numeric(9,6)` | Yes | None | - | Latitude associated with this report. |
| `longitude` | `numeric(9,6)` | Yes | None | - | Longitude associated with this report. |
| `location_source` | `character varying(30)` | **No** | `'unknown'` | - | Provenance origin of coordinates: `photo_exif`, `gps_live`, `historical_inferred`, `user_selected`, `approximate`, `unknown`. |
| `location_accuracy_meters`| `numeric(10,2)` | Yes | None | - | Accuracy of the coordinate in meters (only set for genuine hardware/EXIF sensor readings). |
| `location_captured_at`| `timestamp with time zone` | Yes | None | - | Timestamp when the coordinate itself was captured (sensor/EXIF time). |
| `location_label` | `character varying(255)` | Yes | None | - | Human-readable place name (e.g. from geocoding or place selection) stored for quick admin UI display. |
| `location_evidence` | `text` | Yes | None | - | Explanation of why this location was assigned (e.g. "Matched to GPS sample 20m from photo"). |
| `occurred_at` | `timestamp with time zone` | Yes | None | - | When the event actually happened (may differ from submission time for old photo uploads). |
| `occurred_at_precision`| `character varying(20)` | **No** | `'unknown'` | - | Precision level of `occurred_at`: `exact`, `month`, `year`, `approximate`, `unknown`. |
| `date_source` | `character varying(20)` | **No** | `'unknown'` | - | Origin of the date: `device`, `exif`, `user_entered`, `inferred`, `unknown`. |
| `external_place_id` | `character varying(255)` | Yes | None | - | External Google Place ID if the guide manually searched and selected this POI from autocomplete. |
| `submitted_at` | `timestamp with time zone` | **No** | None | - | Device time when the submission was submitted/queued by the user. |
| `submission_type` | `character varying(100)` | **No** | None | - | Kind of submission: `voice`, `photo`, `note`, or `answer`. |
| `raw_text` | `text` | Yes | None | - | Text note content or transcribed text buffer. |
| `status` | `character varying(50)` | **No** | `'received'` | - | Pipeline state: `received`, `processing`, `extracted`, `failed`. |
| `client_audio_id` | `character varying(255)` | Yes | None | **UNIQUE** | Client-generated UUID for the audio upload step, allowing audio attachment to be retried independently. |
| `audio_storage_key` | `character varying(500)` | Yes | None | - | Server-side cloud storage path (Supabase Storage / local file key) for the audio recording. |
| `audio_content_type`| `character varying(100)` | Yes | None | - | MIME type of the uploaded audio file (e.g. `audio/m4a`, `audio/mp4`). |
| `audio_original_filename`| `character varying(255)` | Yes | None | - | Original filename of the audio track as saved on the device. |
| `audio_size_bytes` | `integer` | Yes | None | - | File size of the audio payload in bytes. |
| `audio_duration_seconds`| `numeric(10,3)` | Yes | None | - | Duration of the audio clip in seconds. |
| `client_photo_id` | `character varying(255)` | Yes | None | **UNIQUE** | Client-generated UUID for the photo upload step, making photo attachment idempotent. |
| `photo_storage_key` | `character varying(500)` | Yes | None | - | Server-side cloud storage path (Supabase Storage / local bucket) for the photo. |
| `photo_content_type`| `character varying(100)` | Yes | None | - | MIME type of the image (e.g. `image/jpeg`). |
| `photo_original_filename`| `character varying(255)` | Yes | None | - | Original image file name. |
| `photo_size_bytes` | `integer` | Yes | None | - | Size of the image file in bytes. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Database row creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Database row update timestamp. |

---

### 4. `transcriptions`
Tracks the asynchronous AI speech-to-text transcription lifecycle for voice submissions.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the transcription job. |
| `submission_id` | `uuid` | **No** | None | **FK** &rarr; `submissions.id` (CASCADE), **UNIQUE** | Reference to the associated voice submission. Exactly one transcription row per submission. |
| `status` | `character varying(20)`| **No** | `'pending'` | - | State machine status: `pending`, `processing`, `completed`, `failed`. |
| `transcript` | `text` | Yes | None | - | The final extracted plain text transcript from the speech audio. |
| `language_code` | `character varying(20)`| Yes | None | - | Detected spoken language code (e.g. `hi-IN`, `ne-NP`, `en-IN`). |
| `language_probability`| `double precision` | Yes | None | - | Model confidence score (0.0 to 1.0) for the detected language. |
| `provider` | `character varying(50)`| **No** | `'sarvam'` | - | The Speech-to-Text provider name (e.g. `sarvam`). |
| `model` | `character varying(50)`| Yes | None | - | Provider model identifier used for transcription. |
| `mode` | `character varying(50)`| Yes | None | - | Transcription mode flags (e.g. `translate`, `transcribe`). |
| `provider_request_id`| `character varying(255)`| Yes | None | - | Provider-returned transaction/request ID for debugging and audits. |
| `error_message` | `text` | Yes | None | - | Sanitized operator-facing error explanation if the STT job failed. |
| `attempt_count` | `integer` | **No** | `0` | - | Number of times transcription processing has been attempted. |
| `started_at` | `timestamp with time zone` | Yes | None | - | Timestamp when the current transcription attempt was sent to the provider. |
| `completed_at` | `timestamp with time zone` | Yes | None | - | Timestamp when the transcription attempt successfully terminated or failed. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Row creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Row update timestamp. |

---

### 5. `extractions`
Tracks the LLM structured fact extraction job for a submission's text content.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the extraction job. |
| `submission_id` | `uuid` | **No** | None | **FK** &rarr; `submissions.id` (CASCADE), **UNIQUE** | Submission whose text is being parsed into structured observations. |
| `status` | `character varying(20)`| **No** | `'pending'` | - | State machine: `pending`, `processing`, `completed`, `failed`. |
| `provider` | `character varying(50)`| **No** | `'anthropic'` | - | AI model provider name (e.g. `anthropic`). |
| `model` | `character varying(100)`| Yes | None | - | LLM model identifier (e.g. `claude-3-5-sonnet-20241022`). |
| `error_message` | `text` | Yes | None | - | Sanitized error message if extraction encountered schema or API failure. |
| `attempt_count` | `integer` | **No** | `0` | - | Count of processing attempts. |
| `started_at` | `timestamp with time zone` | Yes | None | - | When the current extraction attempt was launched. |
| `completed_at` | `timestamp with time zone` | Yes | None | - | When extraction finished producing observations. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Row creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Row update timestamp. |

---

### 6. `observations`
Structured facts and field observations extracted from submissions (e.g. bridge impassable, snowfall at pass).

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique identifier for the observation. |
| `submission_id` | `uuid` | **No** | None | **FK** &rarr; `submissions.id` (CASCADE) | The submission that originated this observation. |
| `guide_id` | `uuid` | **No** | None | **FK** &rarr; `guides.id` (CASCADE) | The guide who witnessed/reported this observation. |
| `knowledge_type_id` | `uuid` | **No** | None | **FK** &rarr; `knowledge_type_config.id` (RESTRICT) | The domain category (e.g. trail condition, water availability, hazard). |
| `latitude` | `numeric(9,6)` | Yes | None | - | WGS-84 latitude where the observation applies. |
| `longitude` | `numeric(9,6)` | Yes | None | - | WGS-84 longitude where the observation applies. |
| `geog` | `geography(POINT, 4326)`| Yes | None | - | PostGIS point geometry for spatial queries and proximity search. |
| `location_source` | `character varying(30)` | Yes | None | - | Snapshot of submission's `location_source` at the moment of extraction. |
| `location_evidence` | `text` | Yes | None | - | Snapshot of reasoning backing the observation's assigned coordinates. |
| `value` | `jsonb` | **No** | None | - | Structured JSON containing observed properties (e.g. `{"status": "muddy", "passable": true}`). |
| `confidence` | `numeric(3,2)` | Yes | None | - | Extractor confidence score between 0.00 and 1.00. |
| `evidence` | `text` | Yes | None | - | Verbatim sentence or quote from transcript justifying this observation. |
| `observed_at` | `timestamp with time zone` | **No** | None | - | Effective timestamp when this observation was valid/observed. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Record creation timestamp. |

---

### 7. `observation_moderation`
Human and automated content review queue for extracted observations before public distribution.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the moderation entry. |
| `observation_id` | `uuid` | **No** | None | **FK** &rarr; `observations.id` (CASCADE), **UNIQUE** | One-to-one relationship ensuring each observation has exactly one moderation record. |
| `status` | `character varying(20)`| **No** | `'pending_review'`| - | Review status: `pending_review`, `approved`, `rejected`. |
| `decided_by` | `character varying(255)`| Yes | None | - | Username or admin ID who made the moderation decision. |
| `decided_at` | `timestamp with time zone` | Yes | None | - | When the moderation decision was made. |
| `rejection_reason` | `character varying(50)`| Yes | None | - | Standardized reason code: `inaccurate`, `unsafe`, `duplicate`, `poor_quality`, `not_useful`, `other`. |
| `rejection_note` | `text` | Yes | None | - | Detailed explanation from the reviewer on why the observation was rejected. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Timestamp when placed in the moderation queue. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Timestamp when moderation state was last changed. |

---

### 8. `locations`
Named places, villages, viewpoints, trailheads, junctions, and points of interest across the trail network.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique identifier for the location. |
| `name` | `character varying(255)` | **No** | None | - | Name of the place (e.g. "Namche Bazaar", "Hillary Bridge"). |
| `description` | `text` | Yes | None | - | Human or web-sourced narrative description of the POI. |
| `latitude` | `numeric(9,6)` | **No** | None | - | WGS-84 latitude. |
| `longitude` | `numeric(9,6)` | **No** | None | - | WGS-84 longitude. |
| `geog` | `geography(POINT, 4326)`| **No** | None | - | PostGIS spatial point for proximity and spatial joins. |
| `source` | `character varying(20)` | **No** | `'manual'` | - | Provenance origin: `'manual'` (human curated) or `'discovered'` (AI/web discovered). |
| `place_kind` | `character varying(50)` | Yes | None | - | Physical type: `bridge`, `cafe`, `viewpoint`, `monastery`, `campsite`, `settlement`. |
| `locality` | `character varying(255)` | Yes | None | - | Reverse-geocoded locality (neighborhood + district) used to scope web searches accurately. |
| `source_urls` | `jsonb` | Yes | None | - | Array of web source URLs citing the existence and location of this place. |
| `discovery_cell_key`| `character varying(32)`| Yes | None | - | Grid cell identifier that originally discovered this POI. |
| `provider` | `character varying(30)` | Yes | None | - | Backend identifier that supplied the place: `google`, `openstreetmap`, `seed`. |
| `external_place_id` | `character varying(255)`| Yes | None | - | Provider's external identifier (e.g. Google Place ID). Paired with `provider` for uniqueness. |
| `google_primary_type`| `character varying(100)`| Yes | None | - | Verbatim primary place type from Google Places API (e.g. `hindu_temple`, `lodging`). |
| `google_types` | `jsonb` | Yes | None | - | Complete list of secondary place types returned by Google Places. |
| `category` | `character varying(50)` | Yes | None | - | TrailMind internal primary classification category (e.g. `Stay`, `Food`, `Hazard`, `Landmark`). |
| `subcategory` | `character varying(50)` | Yes | None | - | TrailMind specific sub-classification category. |
| `formatted_address` | `character varying(500)`| Yes | None | - | Full human-readable street address for admin inspection. |
| `coordinate_confidence`| `character varying(20)`| Yes | None | - | Curator confidence rating: `High`, `Medium`, `Low` (from seed imports). |
| `coordinate_type` | `character varying(50)` | Yes | None | - | Nature of coordinate: `Venue point` (doorstep) vs `Point / area anchor` (general area). |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Record creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Record update timestamp. |

---

### 9. `curated_hubs`
Identifies central anchor locations (e.g. Thamel or Lukla) with a defined operational coverage radius.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the hub definition. |
| `location_id` | `uuid` | **No** | None | **FK** &rarr; `locations.id` (CASCADE), **UNIQUE** | The Location designated as the focal hub. |
| `radius_meters` | `integer` | **No** | `2000` | - | Operating radius around this location (in meters) within which guides receive hub prompts. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Timestamp when hub was created. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Timestamp when hub configuration was updated. |

---

### 10. `location_categories`
TrailMind's controlled category vocabulary — the closed list every category assignment must point at. A catalog (~231 rows), not per-place data; seeded from `app/services/places/category_catalog.py`. Split into two `kind`s: **themes** (what a place is ABOUT — Nature, Religious, Practical) and **place types** (what it literally IS — Temple, Waterfall, Teahouse). That split is what lets one Google type deterministically imply a whole honest category set.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the category. |
| `slug` | `character varying(50)` | **No** | None | **UNIQUE** (`kind`, `slug`) | Stable machine name (`wildlife`, `temple`, `teahouse`). What rules and the AI classifier emit; never matched on display name. Unique per `kind`, not globally — `trail`, `area` and `other` deliberately exist as both a theme and a place type because they name different things. |
| `kind` | `character varying(20)` | **No** | None | **UNIQUE** (`kind`, `slug`), **INDEXED** | `'theme'` or `'place_type'`. |
| `display_name` | `character varying(100)` | **No** | None | - | Human-facing name. For the 16 categories that already existed as `locations.category` values this is byte-identical to the legacy string, so a place's primary theme always reads the same as its legacy category. |
| `default_priority` | `integer` | **No** | None | **CHECK** 0–100 | How much this category matters *in general* — the fallback when nothing place-specific is known. Distinct from an assignment's `relevance`. |
| `description` | `text` | Yes | None | - | Plain-language meaning. Load-bearing rather than decorative: this is the vocabulary definition shown to the AI classifier. |
| `touristlink_id` | `integer` | Yes | None | - | Provenance back to the third-party inventory this vocabulary started from. Never a foreign key; `NULL` marks a category TrailMind added because that inventory lacked it (all trekking, safety and practical vocabulary). |
| `active` | `boolean` | **No** | `true` | - | Retire a category without deleting it — assignments reference it with `RESTRICT`, so deletion would destroy history. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Record creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Record update timestamp. |

---

### 11. `location_category_assignments`
Applies a category to a Location, carrying how much it matters *there*. This is the table that makes a place able to be several things at once — a bazaar is Shopping **and** Food **and** Local Life. Strictly additive: `locations.category`/`subcategory` are unchanged and still written by the same code; the primary assignment of each kind simply mirrors that legacy pair.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the assignment. |
| `location_id` | `uuid` | **No** | None | **FK** &rarr; `locations.id` (CASCADE), **UNIQUE** (`location_id`, `category_id`), **INDEXED** | The place being classified. |
| `category_id` | `uuid` | **No** | None | **FK** &rarr; `location_categories.id` (**RESTRICT**), **INDEXED** | The category applied. RESTRICT, not CASCADE: deleting a catalog entry must never silently delete the assignments that explain places. |
| `kind` | `character varying(20)` | **No** | None | part of partial UNIQUE index | Denormalised from the catalog row, solely so the partial unique index below can enforce one primary *per kind*. A category's kind is fixed at creation, so it cannot drift. |
| `relevance` | `integer` | **No** | None | **CHECK** 0–100 | How much this category matters **for this place**. The place-type assignment anchors the scale at 100; implied themes carry the relevance the catalog declares for that implication. This is what a future live-information view ranks by. |
| `confidence` | `numeric(3,2)` | **No** | None | **CHECK** 0–1 | How trustworthy the *evidence* was — Google's own `primaryType` (0.95) outranks a guess from the place's name (0.75). Deliberately separate from `relevance`: "definitely a cafe, and that barely matters here" and "possibly a viewpoint, and if so it's the whole point" are different statements. |
| `is_primary` | `boolean` | **No** | `false` | **UNIQUE** partial index (`location_id`, `kind`) `WHERE is_primary` | Marks the single most-defining category of each kind. The database guarantees at most one primary theme and one primary place type per Location. |
| `source` | `character varying(20)` | **No** | None | - | How this was established: `seed_type`, `google_type`, `name_rule`, `rule_implied`, `ai`, `manual`. Also an **authority tier** — a pass may only replace assignments of its own tier or below (rules < ai < manual), so the free rule-based pass can never delete a paid model classification or a curator's judgement. |
| `rationale` | `text` | Yes | None | - | Why this was assigned, in words (`"Google type 'hindu_temple'"`, `"implied by place type 'Temple'"`), so a wrong-looking assignment can be traced to the rule that produced it. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Record creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Record update timestamp. |

---

### 12. `poi_discovery`
Tracks grid-cell web research runs that discover unknown places on the map.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the discovery run. |
| `cell_key` | `character varying(32)` | **No** | None | **UNIQUE** | Spatial grid cell key (e.g. `"27.80,86.73"`). Prevents duplicate search costs. |
| `center_latitude` | `numeric(9,6)` | **No** | None | - | Latitude of the spatial center of the grid cell. |
| `center_longitude` | `numeric(9,6)` | **No** | None | - | Longitude of the spatial center of the grid cell. |
| `status` | `character varying(20)` | **No** | `'pending'` | - | State machine: `pending`, `processing`, `completed`, `failed`. |
| `provider` | `character varying(50)` | **No** | `'anthropic'` | - | AI research provider used to process discoveries. |
| `model` | `character varying(100)` | Yes | None | - | Model version used. |
| `error_message` | `text` | Yes | None | - | Error details if discovery failed. |
| `attempt_count` | `integer` | **No** | `0` | - | Number of execution attempts. |
| `discovered_count` | `integer` | **No** | `0` | - | Number of valid new POIs discovered and inserted into `locations`. |
| `discovered_at` | `timestamp with time zone` | Yes | None | - | When the last successful discovery run completed. |
| `started_at` | `timestamp with time zone` | Yes | None | - | Start time of current attempt. |
| `completed_at` | `timestamp with time zone` | Yes | None | - | Finish time of current attempt. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Record creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Record update timestamp. |

---

### 13. `place_question_research`
Tracks the lifecycle of web research conducted about what travellers frequently want to know about a specific place.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the research task. |
| `location_id` | `uuid` | **No** | None | **FK** &rarr; `locations.id` (CASCADE) | The location being investigated. |
| `status` | `character varying(20)` | **No** | `'pending'` | - | State machine: `pending`, `processing`, `completed`, `failed`. |
| `provider` | `character varying(50)` | **No** | `'anthropic'` | - | AI model provider conducting the research. |
| `model` | `character varying(100)` | Yes | None | - | Model name. |
| `error_message` | `text` | Yes | None | - | Error message if research failed. |
| `attempt_count` | `integer` | **No** | `0` | - | Retry attempts counter. |
| `researched_at` | `timestamp with time zone` | Yes | None | - | Timestamp when successful web research was completed. |
| `started_at` | `timestamp with time zone` | Yes | None | - | Timestamp when research execution began. |
| `completed_at` | `timestamp with time zone` | Yes | None | - | Timestamp when research execution concluded. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Record creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Record update timestamp. |

---

### 14. `place_research_findings`
Stores factual statements, summaries, and source citations retrieved from web research regarding a location.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the finding. |
| `location_id` | `uuid` | **No** | None | **FK** &rarr; `locations.id` (CASCADE) | Location this finding applies to. |
| `research_id` | `uuid` | Yes | None | **FK** &rarr; `place_question_research.id` (SET NULL) | The research batch that surfaced this finding. |
| `topic` | `character varying(30)` | **No** | None | - | Stage topic: `'interest'` (general significance) or `'current'` (recent condition checks). |
| `query_text` | `text` | **No** | None | - | Verbatim search query executed against the research API. |
| `provider` | `character varying(50)` | **No** | None | - | Search provider (e.g. `perplexity`, `anthropic`). |
| `model` | `character varying(100)` | Yes | None | - | Specific model used. |
| `summary` | `text` | **No** | None | - | Sanitized summary of the findings from the web search. |
| `source_urls` | `jsonb` | Yes | None | - | Array of cited web page URLs. |
| `source_titles` | `jsonb` | Yes | None | - | Titles of the cited web pages. |
| `retrieved_at` | `timestamp with time zone` | **No** | None | - | Timestamp when the search was executed (evidence freshness). |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Row creation timestamp. |

---

### 15. `place_questions`
Targeted place-specific inquiries presented to guides when they are physically at that location.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the place question. |
| `location_id` | `uuid` | **No** | None | **FK** &rarr; `locations.id` (CASCADE) | Location where this question is triggered. |
| `question_text` | `text` | **No** | None | - | Present-tense question asked to the guide (e.g. "How does Hillary Bridge look today?"). |
| `normalized_text` | `text` | **No** | None | **UNIQUE** (`location_id`, `normalized_text`) | Normalized text (lowercase, stripped punctuation) ensuring questions aren't duplicated at one POI. |
| `contribution_kind`| `character varying(20)` | **No** | `'observation'` | - | Expected response format: `photo`, `voice`, `observation`, `experience`, `status`. |
| `context_note` | `text` | Yes | None | - | Grounded explanation for why this is being asked (e.g. "Hikers often worry about high wind swaying"). |
| `display_order` | `integer` | **No** | `0` | - | Ranking order within the place's inquiry card stack. |
| `source_urls` | `jsonb` | Yes | None | - | Provenance web URLs supporting the question. |
| `source_finding_id`| `uuid` | Yes | None | **FK** &rarr; `place_research_findings.id` (SET NULL) | Direct link to the research finding that justified creating this question. |
| `research_batch_id`| `uuid` | Yes | None | - | Identifier grouping questions created in the same generation run. |
| `source` | `character varying(20)` | **No** | `'ai_research'` | - | Provenance: `'ai_research'` or `'seed'` (curated manual questions). |
| `active` | `boolean` | **No** | `true` | - | Whether this question is active. Deactivated when superseded by newer research batches. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Record creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Record update timestamp. |

---

### 16. `knowledge_type_config`
Configures policy, refresh intervals, and safety criticality for each knowledge category.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique identifier for the knowledge type config. |
| `knowledge_type` | `character varying(100)`| **No** | None | **UNIQUE** | Slug key: `weather`, `trail_condition`, `snow_ice`, `water_availability`, `hazard`. |
| `display_name` | `character varying(255)`| **No** | None | - | User-facing display title for this knowledge domain. |
| `freshness_window_hours`| `integer` | **No** | None | - | Number of hours before an observation is considered stale and needs re-verification. |
| `aging_threshold_hours` | `integer` | Yes | None | - | Threshold in hours where knowledge transitions from fresh to aging (pre-stale warning). |
| `geographic_relevance_radius_meters`| `integer` | **No** | None | - | Distance in meters over which an observation in this category remains spatially valid. |
| `default_priority` | `integer` | **No** | `0` | - | Base priority score when computing gap priority rankings. |
| `safety_critical` | `boolean` | **No** | `false` | - | Flags whether this data is critical for trek safety (elevates question ranking and point rewards). |
| `active` | `boolean` | **No** | `true` | - | Whether this knowledge type is actively tracked. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Record creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Record update timestamp. |

---

### 17. `questions`
Questions dynamically generated to fill detected knowledge gaps on the trail network.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the question. |
| `client_request_id` | `character varying(255)`| Yes | None | **UNIQUE** | Client-supplied idempotency key preventing duplicate question generation. |
| `knowledge_type_id` | `uuid` | **No** | None | **FK** &rarr; `knowledge_type_config.id` (RESTRICT) | The knowledge gap category being filled. |
| `gap_state` | `character varying(20)` | **No** | None | - | Snapshot of gap condition at generation time: `missing`, `stale`, or `aging`. |
| `target_latitude` | `numeric(9,6)` | **No** | None | - | Latitude where the knowledge gap exists. |
| `target_longitude` | `numeric(9,6)` | **No** | None | - | Longitude where the knowledge gap exists. |
| `nearest_known_place_name`| `character varying(255)`| Yes | None | - | Denormalized snapshot of the nearest named location for context. |
| `nearest_known_place_distance_meters`| `double precision`| Yes | None | - | Distance in meters to the nearest named location at generation time. |
| `safety_critical` | `boolean` | **No** | None | - | Snapshot of whether the underlying gap was marked safety critical. |
| `default_priority` | `integer` | **No** | None | - | Snapshot of the base priority score. |
| `staleness_severity_hours`| `double precision`| **No** | `0.0` | - | How many hours past freshness expiration this data point was. |
| `gap_rank` | `integer` | **No** | None | - | Calculated integer ranking of the gap at generation time. |
| `question_text` | `text` | Yes | None | - | Generated natural language question text directed at the guide. |
| `short_context` | `text` | Yes | None | - | Brief background explaining why the question is being asked. |
| `status` | `character varying(20)` | **No** | `'pending'` | - | State machine: `pending`, `processing`, `generated`, `failed`. |
| `provider` | `character varying(50)` | **No** | `'anthropic'` | - | AI model provider generating the question. |
| `model` | `character varying(100)`| Yes | None | - | Specific model used. |
| `error_message` | `text` | Yes | None | - | Sanitized error details if question generation failed. |
| `attempt_count` | `integer` | **No** | `0` | - | Number of generation attempts. |
| `started_at` | `timestamp with time zone` | Yes | None | - | Timestamp when generation attempt began. |
| `completed_at` | `timestamp with time zone` | Yes | None | - | Timestamp when question text was produced and saved. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Record creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Record update timestamp. |

---

### 18. `question_assignments`
Dispatches questions to individual guides on the trail.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the assignment. |
| `question_id` | `uuid` | **No** | None | **FK** &rarr; `questions.id` (CASCADE) | The question being assigned. |
| `guide_id` | `uuid` | **No** | None | **FK** &rarr; `guides.id` (CASCADE) | The guide chosen to answer this question. |
| `status` | `character varying(20)` | **No** | `'assigned'` | - | Assignment state: `assigned`, `active`, `completed`, `cancelled`. |
| `assigned_at` | `timestamp with time zone` | **No** | None | - | Timestamp when the assignment was issued to the guide. |
| `answered_at` | `timestamp with time zone` | Yes | None | - | Timestamp when the guide answered the assignment. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Record creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Record update timestamp. |

---

### 19. `question_answers`
Stores the guide's explicit text answer to an assigned question.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the answer record. |
| `question_id` | `uuid` | **No** | None | **FK** &rarr; `questions.id` (CASCADE) | The question that was answered. |
| `assignment_id` | `uuid` | **No** | None | **FK** &rarr; `question_assignments.id` (CASCADE) | The specific assignment that is satisfied by this answer. |
| `guide_id` | `uuid` | **No** | None | **FK** &rarr; `guides.id` (CASCADE) | The answering guide. |
| `client_answer_id` | `character varying(255)`| **No** | None | **UNIQUE** | Client-generated UUID ensuring answer submissions are strictly idempotent. |
| `answer_text` | `text` | **No** | None | - | Verbatim response text supplied by the guide. |
| `submission_id` | `uuid` | **No** | None | **FK** &rarr; `submissions.id` (CASCADE) | Associated submission entity routing this answer through the standard extraction pipeline. |
| `answered_at` | `timestamp with time zone` | **No** | None | - | Time on guide's device when the answer was finalized. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Database row creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Database row update timestamp. |

---

### 20. `reward_rules`
Defines point reward rates and criteria for different contributions.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the rule. |
| `rule_key` | `character varying(100)`| **No** | None | **UNIQUE** | Unique rule identifier (e.g. `question_answer`, `place_question_photo`, `explore_contribution`). |
| `points` | `integer` | **No** | None | - | Point value awarded when this rule is triggered. |
| `description` | `text` | Yes | None | - | Description of the action required to earn these points. |
| `active` | `boolean` | **No** | `true` | - | Whether this reward rule is currently active. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Row creation timestamp. |
| `updated_at` | `timestamp with time zone` | **No** | `now()` | - | Row update timestamp. |

---

### 21. `reward_ledger`
Immutable, append-only ledger tracking points granted to guides.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `uuid` | **No** | `uuid_generate_v4()` | **PK** | Unique primary key for the ledger transaction. |
| `guide_id` | `uuid` | **No** | None | **FK** &rarr; `guides.id` (CASCADE) | The guide who earned the reward. |
| `points` | `integer` | **No** | None | - | Number of points awarded (immutable copy from the rule at award time). |
| `rule_key` | `character varying(100)`| **No** | None | - | The rule key under which the points were granted. |
| `idempotency_key` | `character varying(255)`| **No** | None | **UNIQUE** | Unique idempotency key (reuses client IDs) preventing duplicate awards on retried syncs. |
| `source_type` | `character varying(50)` | **No** | None | - | Event type: `question_answer`, `place_question_answer`, `explore_submission`. |
| `source_id` | `uuid` | Yes | None | - | UUID of the underlying answer or submission entity. |
| `awarded_at` | `timestamp with time zone` | **No** | `now()` | - | Timestamp when the reward was credited. |
| `created_at` | `timestamp with time zone` | **No** | `now()` | - | Row insertion timestamp. |

---

### 22. `alembic_version`
Internal version tracking for Alembic schema migrations.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `version_num` | `character varying(32)`| **No** | None | **PK** | Current migration revision hash applied to the database. |

---

### 23. `spatial_ref_sys`
Standard PostGIS spatial reference system lookup catalog.

| Column | Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `srid` | `integer` | **No** | None | **PK** | Spatial Reference Identifier (e.g. `4326` for WGS 84). |
| `auth_name` | `character varying(256)`| Yes | None | - | Name of the projection authority (e.g. `EPSG`). |
| `auth_srid` | `integer` | Yes | None | - | Authority-specific SRID code. |
| `srtext` | `character varying(2048)`| Yes| None | - | Well-Known Text (WKT) representation of the coordinate reference system. |
| `proj4text` | `character varying(2048)`| Yes| None | - | Proj4 projection parameter definition string. |

---

## 3. Summary Metrics
- **Total Base Tables**: 23
- **Domain Tables**: 21
- **Infrastructure / Spatial Tables**: 2 (`alembic_version`, `spatial_ref_sys`)
- **Total Columns Documented**: 275
