# AI Trail Reporter — Mobile

Offline-first guide app. React Native + Expo + TypeScript, with a local SQLite
database as the persistence layer and a user-initiated **outbox sync** to the
FastAPI backend (Step 5: text notes; Step 6: GPS location samples; Step 7: voice
recordings; Step 8: on-demand transcription status).

## Why this app is location-first

The product's core relationship is **knowledge need → geographic area → relevant
guide**, not trek → route segment → question. Concretely, that means the app never
asks a guide to pick a trek or route before it can be useful. Instead:

```
Guide opens the app
    -> GPS location is captured (Step 6: on demand, in the foreground)
    -> Stored locally, then synced to the backend
    -> Backend resolves geographic context from the guide's actual location
    -> (Later steps) the system figures out what knowledge is needed there
```

A guide's location is a fact about where they physically are, discovered from GPS —
never a route they selected from a list. This step does not add trek/route
selection, a route dropdown, or any mandatory destination setup, and it isn't
supposed to.

## Stack

- React Native (Expo SDK 57, `expo ~57.0.16`)
- TypeScript (strict mode)
- `expo-sqlite` for on-device persistence
- `expo-crypto` for client-generated UUIDs (`Crypto.randomUUID()`) — the SDK-native
  mechanism; no third-party UUID library was added
- `expo-location` for foreground-only GPS capture — see
  [Foreground location capture](#foreground-location-capture) and
  [Permission flow](#permission-flow)
- `expo-audio` for foreground-only voice recording — see
  [Voice recording](#voice-recording-step-7)
- `expo-file-system` (its new class-based `File` API) — only used for best-effort
  cleanup of an orphaned recording if saving its SQLite metadata fails; the actual
  upload never reads a recording into a JS string, it hands the file URI straight
  to `fetch`/`FormData`
- The built-in `fetch` API for talking to the backend — no HTTP client library
- `react-native-safe-area-context` for real safe-area insets (Step 15)
- `@expo/vector-icons` for iconography (Step 15) — replaces emoji-as-UI
- `expo-font` + `@expo-google-fonts/bricolage-grotesque` +
  `@expo-google-fonts/atkinson-hyperlegible` for the app's two typefaces
  (Step 15) — see [UI/UX redesign](#uiux-redesign-step-15)

No navigation library, no state-management library — see [Project layout](#project-layout).

## Install & run

```
cd mobile
npm install
npx expo start
```

Then open the app in Expo Go (scan the QR code), an iOS simulator, or an Android
emulator. `npx expo start --web` also works for everything except GPS capture
(`expo-location` needs a native module; `expo-sqlite`'s web backend is also alpha in
this Expo SDK).

Configure the backend URL before syncing — see
[Configuring the backend URL](#configuring-the-backend-url) below. Everything else
(guide setup, notes, capturing a location, viewing local data) works with zero
configuration and no backend running at all.

### Required Expo configuration for location permission

[`app.json`](app.json) declares the `expo-location` config plugin with a
foreground-only permission message:

```json
["expo-location", { "locationWhenInUsePermission": "…" }]
```

No `isAndroidBackgroundLocationEnabled`, `isIosBackgroundLocationEnabled`, or
`locationAlwaysAndWhenInUsePermission` option is set — deliberately, since those are
what add `ACCESS_BACKGROUND_LOCATION` (Android) and `UIBackgroundModes: ["location"]`
(iOS) to the built app. This was checked directly against the plugin's source (not
assumed) — see [Architectural decisions](#architectural-decisions-relevant-to-step-6)
below.

### Required Expo configuration for microphone permission (Step 7)

[`app.json`](app.json) also declares the `expo-audio` config plugin:

```json
["expo-audio", { "microphonePermission": "…", "enableBackgroundRecording": false }]
```

`enableBackgroundRecording` is explicitly set to `false` (not just left at its
default) so the "no background recording" decision is visible in configuration,
matching Step 6's foreground-only precedent for location.

## The role of SQLite

All data the guide creates on this device — their local profile and every capture or
location — is stored in a local SQLite database via `expo-sqlite`, in
[`src/db/database.ts`](src/db/database.ts). The database is opened through
`<SQLiteProvider databaseName="trailreporter.db" onInit={migrateDbIfNeeded}>` in
[`App.tsx`](App.tsx), and schema setup runs once via `migrateDbIfNeeded`, tracked
with SQLite's built-in `PRAGMA user_version`:

- On a fresh install, `user_version` starts at `0` and every step below runs in
  order, ending at the current version.
- On a later launch, already-applied steps are skipped — a step only runs once.
- Every step is additive (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ADD COLUMN`,
  `CREATE UNIQUE INDEX IF NOT EXISTS`) — reopening the app never drops or resets
  existing data. Future schema changes get a new `if (currentDbVersion === N)` step,
  appended after the existing ones — never edit an already-shipped step.

Current version: **4**.

- **v1** (Step 4): creates `local_guide` and `local_capture`.
- **v2** (Step 5): adds `local_guide.client_guide_id`; adds
  `local_capture.client_submission_id`, `server_submission_id`,
  `last_sync_error`, `sync_attempt_count`; backfills a stable client id onto any
  pre-existing row that predates the column; adds unique indexes on both new
  client-id columns.
- **v3** (Step 6): creates `local_location` (a brand-new table — no backfill needed,
  every row gets a `client_location_id` at insert time from day one), plus its
  unique index on `client_location_id` and two lookup indexes.
- **v4** (Step 7): adds `local_capture.local_audio_uri`, `client_audio_id`,
  `audio_duration_millis`, `audio_content_type` — all nullable, no backfill needed
  (only ever set for newly-created `'voice'` rows going forward, so every
  pre-existing `'note'` row correctly stays `NULL` forever, not "not yet
  backfilled"); adds a unique index on `client_audio_id`.

This is a **device-local** database, unrelated to the backend's PostgreSQL/PostGIS
database.

## Local tables

**`local_guide`** — the guide profile for this device (Step 4 assumes one guide per
device):

| column              | notes                                                                                     |
|---------------------|---------------------------------------------------------------------------------------------|
| `id`                | local SQLite row id                                                                        |
| `client_guide_id`   | stable UUID, generated once on this device — see [Client vs. server ids](#client-ids-vs-server-ids) |
| `server_guide_id`   | nullable — populated once this profile is confirmed on the backend                        |
| `name`              | required                                                                                   |
| `phone_number`      | optional                                                                                   |
| `created_at` / `updated_at` | ISO-8601 strings                                                                    |

**`local_capture`** — a text note *or* (Step 7) a voice recording captured on this
device, to be sent to the server:

| column                  | notes                                                                                 |
|-------------------------|------------------------------------------------------------------------------------------|
| `id`                    | local SQLite row id                                                                     |
| `local_guide_id`        | references `local_guide.id`                                                             |
| `client_submission_id`  | stable UUID, generated once when the capture is created — makes creating the server `Submission` idempotent, for both notes and voice |
| `server_submission_id`  | nullable — populated once the backend confirms receipt                                  |
| `capture_type`          | `'note'` or `'voice'` (`'photo'` / `'mixed'` are reserved future values, see [`src/types/models.ts`](src/types/models.ts)) |
| `text_content`          | the note text — always `NULL` for a `'voice'` row                                       |
| `local_audio_uri`       | (Step 7) on-device file path of the recording — always `NULL` for a `'note'` row. The audio bytes themselves are never stored in SQLite, only this path — see [Voice recording](#voice-recording-step-7) |
| `client_audio_id`       | (Step 7) a **second, distinct** stable UUID from `client_submission_id`, generated once at recording time — makes the audio *upload* step (a separate backend request from creating the submission) independently idempotent. Always `NULL` for a `'note'` row |
| `audio_duration_millis` | (Step 7) whatever `expo-audio` actually reported when recording stopped — never fabricated, may be `NULL` |
| `audio_content_type`    | (Step 7) e.g. `'audio/m4a'` — always `NULL` for a `'note'` row                          |
| `sync_status`           | see [Sync status meanings](#sync-status-meanings)                                       |
| `sync_attempt_count`    | incremented every time a sync attempt is made for this row (success or failure)         |
| `last_sync_error`       | user-safe message from the most recent failed attempt; cleared on success               |
| `created_at` / `updated_at` | ISO-8601 strings                                                                    |

**`local_location`** — a GPS sample captured on this device (Step 6), mirroring
`local_capture`'s outbox shape exactly:

| column                  | notes                                                                                 |
|-------------------------|------------------------------------------------------------------------------------------|
| `id`                    | local SQLite row id                                                                     |
| `local_guide_id`        | references `local_guide.id`                                                             |
| `client_location_id`    | stable UUID, generated once when the sample is captured                                 |
| `server_location_id`    | nullable — populated once the backend confirms receipt                                  |
| `latitude` / `longitude`| the captured coordinate                                                                 |
| `accuracy_meters`       | nullable — the device-reported accuracy radius, in meters, if the OS provided one; see [GPS accuracy](#gps-accuracy) |
| `recorded_at`           | ISO-8601 — when the *device* fixed this location, not when it was saved or sent         |
| `sync_status`           | see [Sync status meanings](#sync-status-meanings)                                       |
| `sync_attempt_count`    | incremented every time a sync attempt is made for this row (success or failure)         |
| `last_sync_error`       | user-safe message from the most recent failed attempt; cleared on success               |
| `created_at` / `updated_at` | ISO-8601 — this local row's own bookkeeping timestamps, distinct from `recorded_at` |

Indexed on `client_location_id` (unique), `(local_guide_id, sync_status)`, and
`(local_guide_id, recorded_at)`.

## Client ids vs. server ids

There are two independent id systems, and they must never be confused:

- **Local row id** (`local_guide.id`, `local_capture.id`, `local_location.id`) — a
  SQLite auto-increment integer, meaningless outside this device. Never sent to the
  API.
- **Client id** (`client_guide_id`, `client_submission_id`, `client_location_id`,
  and — Step 7 — `client_audio_id`) — a UUID generated once on this device (via
  `expo-crypto`, see [`src/db/uuid.ts`](src/db/uuid.ts)) at the moment the row is
  first created, and **never regenerated** afterwards. This is what's sent to the
  backend to make creation idempotent (see
  [Why idempotency is necessary](#why-idempotency-is-necessary)). A voice capture
  gets **two** client ids at creation time, not one: `client_submission_id` (makes
  creating the `Submission` idempotent) and `client_audio_id` (makes the separate
  audio-upload request idempotent) — see
  [Audio idempotency](#audio-idempotency-step-7).
- **Server id** (`server_guide_id`, `server_submission_id`, `server_location_id`) —
  the backend's UUID primary key, only known once the backend has actually
  confirmed the record. `NULL` until then. There is no separate "server audio id"
  — the audio is a property of the server `Submission` (see `backend/README.md`).

## Why idempotency is necessary

Mobile networks fail in the worst possible place: *after* the server has done the
work but *before* the phone finds out. Concretely, for a GPS sample:

```
Phone --POST /api/v1/guides/{id}/locations--> Server
                                                Server saves the sample successfully
      <--- connection drops before the response arrives ---
Phone still thinks the request failed (or doesn't know) -> retries
```

Unlike a note (which a person typed and would probably notice duplicated), the same
physical GPS sample can be retried without the guide ever knowing — so this matters
even more for locations. A naive retry would create a second, duplicate
`GuideLocation` row. To prevent that, every create request carries a **stable,
client-generated id** generated once and stored locally —`client_guide_id` for
guides, `client_submission_id` for notes, `client_location_id` for GPS samples. The
backend enforces uniqueness on each with a real PostgreSQL unique constraint (not
just an app-level check) and, on a repeat, returns the existing record instead of
creating another; a repeat with *different* data for the same id is rejected
(`409`) rather than silently overwriting the original — see `backend/README.md` for
the server side of this. This was verified against real concurrent requests and a
real database; see [Idempotency testing](#idempotency-testing-results) below.

## Foreground location capture

[`src/location/locationService.ts`](src/location/locationService.ts) is the only
file that calls `expo-location` — screens never call the location API directly, the
same rule as SQLite (repositories) and the backend (`src/api/`).
`captureCurrentLocation()`:

1. Checks foreground permission (`getForegroundPermissionsAsync`); requests it
   (`requestForegroundPermissionsAsync`) only if not already granted.
2. If still not granted, returns `{ status: 'permission-denied', canAskAgain }` —
   nothing is captured or stored.
3. Otherwise calls `getCurrentPositionAsync()` — a one-shot, foreground fix. No
   continuous/background tracking, no `expo-task-manager`, no geofencing.
4. Validates the returned coordinate is actually in range (`-90..90` /
   `-180..180`); an out-of-range or missing result is reported as
   `{ status: 'error', message }`, never silently treated as success.
5. On success, returns only what the app needs — `latitude`, `longitude`,
   `accuracyMeters` (nullable), and `recordedAt` (the device's fix `timestamp`
   converted to an ISO-8601 string).

This never fabricates a result. A denied permission or a device/API failure is
always reported as such — the caller (`HomeScreen`) shows the real outcome, and no
row is written to `local_location` unless step 5 above actually happened.

## Permission flow

Foreground location permission is requested **only** as a direct result of tapping
"Capture location" on the Home screen — never proactively, never repeatedly without
new user intent:

- **Granted already:** capture proceeds immediately.
- **Not yet asked:** the OS permission prompt appears as part of this same tap;
  granting it lets capture proceed in the same action.
- **Denied:** no local row is created. If the OS says the user can be asked again
  (`canAskAgain`), the UI says permission is required and to try again; if not
  (permanently denied), the UI says to enable it in device settings — it does not
  keep re-prompting on every tap.
- **Device can't get a fix:** no local row is created; the UI shows the real error
  message. Existing stored locations are completely untouched either way.

Only foreground permission is ever requested — no background permission dialog
exists in this build.

## Local GPS capture flow

```
Tap "Capture location" (Home screen)
    -> locationService.captureCurrentLocation()
         -> permission check/request (foreground only)
         -> getCurrentPositionAsync()
         -> validate coordinate range
    -> on success: locationRepository.createLocation(...)
         -> INSERT into local_location, client_location_id generated here
         -> sync_status = 'pending'
    -> UI shows "Location captured locally — not yet sent to the server."
```

The sample is durable on the device (a committed SQLite row) before anything
network-related is ever attempted — capture never waits on, or depends on, a
successful network call.

## Voice recording (Step 7)

[`src/audio/audioRecordingService.ts`](src/audio/audioRecordingService.ts) is the
dedicated recording service — the same rule as `expo-location`/`expo-sqlite`: raw
`expo-audio` API calls live in one place, not scattered across screens. The one
unavoidable exception: `expo-audio`'s recorder instance must be created via its
`useAudioRecorder` hook, which only works inside a React component, so
[`src/components/VoiceRecorderCard.tsx`](src/components/VoiceRecorderCard.tsx)
calls that hook and hands the resulting recorder object into the service — every
actual decision (permission handling, when to call `record()`/`stop()`, how to
shape the result) still lives in the service, not the component.

**Why recordings are saved to the document directory, not the cache directory.**
`expo-audio` saves recordings to the app's cache directory by default, and the
docs are explicit that the OS may delete cache files under storage pressure. A
recording that's pending sync must survive that, so `RECORDING_OPTIONS` in
`audioRecordingService.ts` passes `{ ...RecordingPresets.HIGH_QUALITY, directory:
'document' }` — the app's persistent document directory instead.

**Recording format.** `RecordingPresets.HIGH_QUALITY` produces a `.m4a` file
(`audio/m4a`) on both iOS and Android — a fixed, documented fact about that
preset, not a guess. The original recording is preserved as-is; nothing
transcodes it (there is no reason to yet — Saaras integration is a later step).

### Microphone permission flow

Requested **only** as a direct result of tapping "Record voice note" — never
proactively, never repeatedly without new user intent (same rule as location):

- **Granted already:** recording starts immediately.
- **Not yet asked:** the OS permission prompt appears as part of this same tap;
  granting it lets recording start in the same action.
- **Denied:** no recording starts, no local row is created. If the OS says the
  user can be asked again, the UI says permission is required and to try again;
  if not, the UI says to enable it in device settings.
- **Recording fails to start or stop cleanly:** no local row is created; the UI
  shows the real error message. Existing stored recordings are untouched either
  way.

Only foreground/in-app recording is ever requested — no background-recording
permission or capability exists in this build (`enableBackgroundRecording:
false` in `app.json`).

### Recording flow

```
Tap "Record voice note" (VoiceRecorderCard)
    -> audioRecordingService.startRecording(recorder)
         -> permission check/request
         -> setAudioModeAsync({ allowsRecording: true, ... })
         -> recorder.prepareToRecordAsync(); recorder.record()
    -> UI shows "● Recording…" and a live duration timer
Tap "Stop"
    -> audioRecordingService.stopRecording(recorder, lastKnownDurationMillis)
         -> recorder.stop()
         -> reads recorder.uri -- if missing, reports an error, nothing is saved
    -> on success: captureRepository.createVoiceCapture(...)
         -> INSERT into local_capture (capture_type='voice'), client_submission_id
            AND client_audio_id both generated here
         -> sync_status = 'pending'
    -> UI shows "Voice note saved locally — pending sync."
```

**"Recording successfully" means two things both happened:** the audio file was
created on disk (`recorder.stop()` succeeded and produced a real `uri`) **and**
the SQLite metadata row was committed. Never presented as a successful save
unless both are true — see [Task G cleanup](#audio-file-vs-sqlite-write-failure)
below for what happens if only the first one succeeds.

### Audio file vs. SQLite write failure

If the audio file is created but the subsequent `local_capture` insert throws
(disk full, an unexpected SQLite error, etc.), `VoiceRecorderCard` catches it,
attempts a best-effort cleanup — `new File(uri).delete()` via `expo-file-system`
— so the orphaned file doesn't sit on disk unreferenced, and shows a truthful
"could not save" error. It never reports success in this case, and the cleanup
attempt's own failure (if the delete itself throws) is logged but doesn't change
the user-facing error.

## The outbox / sync flow

Sync is **user-initiated** ("Sync now" on the Home screen) — there is no background
sync, no connectivity listener, no automatic retry scheduler in this step. The whole
flow lives in [`src/sync/syncService.ts`](src/sync/syncService.ts), `syncAll(db)`,
and covers notes, voice recordings, and GPS samples through the same engine (not a
third, competing sync system):

```
STEP 1  Find the current local guide.
        No guide? -> return a clean "nothing to sync" result. Done.

STEP 2  Does the guide already have a server_guide_id?
          yes -> use it, skip straight to STEP 3.
          no  -> POST /api/v1/guides with { name, phone_number, client_guide_id }.
                 On success, save the returned id as server_guide_id.
                 On failure -> stop here. Nothing else is touched.

STEP 3  Synchronize eligible captures -- notes AND voice recordings together, in
        ONE oldest-created_at-first loop (status 'pending', 'failed', or a
        leftover 'uploading' -- see Crash recovery below). Each is independent;
        results are split by type afterward purely for reporting (STEP 5).
          - a NOTE: POST /api/v1/submissions with client_submission_id and the
            note text. One request.
          - a VOICE recording: TWO requests, both idempotent (see
            [Audio idempotency](#audio-idempotency-step-7)):
              1. POST /api/v1/submissions with client_submission_id,
                 capture_type 'voice', text_content omitted -- resolves/creates
                 the server Submission.
              2. POST /api/v1/submissions/{id}/audio with client_audio_id and
                 the audio file -- uploads and attaches the audio.
            Only after BOTH succeed is the capture marked 'uploaded'. If step 1
            succeeds but step 2 throws, the capture is marked 'failed' and BOTH
            steps are retried from scratch next sync -- safe and cheap, because
            step 1 is itself idempotent (the backend just returns the already-
            resolved submission).
        Either way: on success store server_submission_id and mark 'uploaded';
        on failure store the error and mark 'failed'. One capture failing does
        not stop the rest.

STEP 4  Synchronize eligible GPS locations, same eligibility rule, oldest
        recorded_at first (not created_at -- the device's fix time is what orders
        location history downstream). For each, independently: mark 'uploading',
        increment sync_attempt_count, POST /api/v1/guides/{server_guide_id}/locations
        with client_location_id; on success store server_location_id and mark
        'uploaded'; on failure store the error and mark 'failed'. One location
        failing does not stop the rest, and does not affect captures or vice versa.

STEP 5  Return a structured SyncResult: { guideSynced, guideError,
        notes: { attempted, uploaded, failed, outcomes },
        voice: { attempted, uploaded, failed, outcomes },
        locations: { attempted, uploaded, failed, outcomes }, message }.
        `notes` and `voice` are DISTINCT summaries, not a merged "captures"
        bucket, even though STEP 3 processes them in one interleaved loop --
        the UI renders `message` directly and can report on each kind
        separately; it never parses logs.
```

**Why notes and voice share one loop instead of two sequential passes.** Both are
rows in the same `local_capture` table, fetched by the same
`listSyncableCaptures()` query, oldest-first. Splitting them into "all notes, then
all voice" would need a second query and would sync a guide's captures out of the
order they were actually made, for no benefit — each item's HTTP call and local
state update are already fully independent (wrapped in their own try/catch), so a
slow or failing voice upload can't block a note, or vice versa, regardless of
interleaving.

**Failure policy — `failed`, not back to `pending`.** When an item's upload attempt
fails, it's marked `failed` rather than reset to `pending`. This makes "never
attempted" and "attempted and didn't work" distinguishable in the UI (via
`last_sync_error`), while remaining exactly as retryable as `pending` — both are
included in the next sync's eligible set. Applies identically to notes and
locations.

**One failure doesn't stop the run** — for any note, any voice recording, any
location, and across all three: a failed voice upload doesn't block a note or a
location, and vice versa. Each item's HTTP call(s) and local state update are
wrapped independently.

**Crash recovery.** The in-process sync lock (below) only prevents two concurrent
`syncAll()` calls in the *same* app session — it doesn't survive the app being
killed. If that happens mid-request, an item can be left at `'uploading'` with no
request actually in flight anymore. Since eligible items are only read once, at the
very start of a fresh `syncAll()` run, anything already `'uploading'` at that moment
can only be such a leftover — so it's included and retried. Applies to
`local_capture` (notes and voice) and `local_location` identically. This was
specifically tested for all three; see [Tests actually run](#tests-actually-run).
For a voice recording specifically, this covers **Case D** from Step 7's crash-
boundary analysis — sync started, the server Submission was created, then the app
was killed before the audio upload completed: on restart, the capture is still
`'uploading'`, gets retried from STEP 3.1 above, and step 1 (resolve the
submission) is itself idempotent — so retrying from scratch is always safe, never
creates a second submission.

## Audio idempotency (Step 7)

Two separate backend requests happen per voice recording (create the submission,
then upload its audio), and each needs its own idempotency guarantee — reusing
`client_submission_id` for both would conflate "did we create the submission" with
"did we attach the audio," which are genuinely different questions with different
answers when a request is retried mid-flow. So:

- **`client_submission_id`** makes "resolve/create the server Submission" safe to
  repeat. Reused across retries exactly like a note's.
- **`client_audio_id`** makes "attach audio to that submission" safe to repeat,
  *independently*. Generated once, at recording time, in
  `captureRepository.createVoiceCapture()` — never regenerated.

This directly answers the failure scenario in the Step 7 spec: *"request succeeds
on the server, audio is stored, the network response is lost, mobile retries."*
Retrying re-sends the same `client_submission_id` (backend returns the same
existing submission, HTTP 200 — no duplicate) and the same `client_audio_id` (backend
recognizes it already attached exactly this audio, returns the existing reference,
HTTP 200 — **does not write a second file to server storage**). A submission that
already has *different* audio attached under a *different* `client_audio_id`
rejects the new attempt with `409 Conflict` — this build does not support
replacing an already-attached recording. See `backend/README.md`'s "Upload audio
for a voice submission" section for the server-side mechanics (including the row-
level locking that makes this safe even under genuinely concurrent retries — 5
real concurrent identical upload requests were tested; exactly one `201` + four
`200`s, exactly one file written).

## Concurrent sync protection

`syncAll()` keeps a single in-process lock (a shared promise) covering the *entire*
run — guide, notes, voice recordings, and locations together. If "Sync now" is
tapped again while a sync is already running, the second call receives the *same*
in-flight result instead of starting an independent run that could race the first
(and, in particular, cannot start a second, competing audio upload for the same
capture). The Home screen also
disables the button and shows a spinner while syncing, as a second layer of
protection. This is a simple in-memory lock, appropriate for one device/one process
— not a distributed lock, and it isn't meant to be one.

## Sync status meanings

Identical semantics for `local_capture` (notes and voice) and `local_location`:

| status      | meaning                                                                              |
|-------------|----------------------------------------------------------------------------------------|
| `pending`   | Stored safely on the phone, never yet attempted.                                       |
| `uploading` | A sync attempt is currently sending it (or was interrupted mid-attempt — see crash recovery above). For voice, this covers BOTH the submission-creation and audio-upload requests — it does not distinguish which sub-step is in flight. |
| `uploaded`  | **The backend has received and persisted it.** For voice, this means BOTH the submission exists AND its audio is confirmed durably stored — never set after only the submission succeeds. See below for what it does NOT mean. |
| `failed`    | The last attempt failed. Still stored locally (including the audio file, for a voice recording), still retryable.                        |

`processing`, `synced`, and `dead_letter` are declared in
[`src/types/models.ts`](src/types/models.ts) for future steps but are never produced
by this build.

**What `uploaded` does NOT mean:** transcribed, extracted, turned into a structured
observation, accepted into the knowledge base, resolved into geographic context, or
"done." For a location, `uploaded` means the coordinate and timestamp are durably in
PostgreSQL. For a voice recording, `uploaded` means the audio file is durably stored
on the backend and referenced from its `Submission` row — **nothing has listened to
it, transcribed it, or extracted anything from it.** AI processing doesn't exist
yet — see [Status: what this step does and does not do](#status-what-this-step-does-and-does-not-do).

## Local capture vs. server upload — the UI is explicit about the difference

The Home screen's location card always shows one of two distinct sync states next to
the coordinate, never a single ambiguous "done":

- **"📍 Captured locally — waiting to send"** (or "⚠️ … last send failed, will
  retry") — this device has it, the server does not yet.
- **"✅ Uploaded to server"** — confirmed received by the backend.

A successful local capture is never presented as if it reached the server — those
are two separate, truthfully-labeled states, both before and after "Sync now" is
pressed. The same principle applies to voice: `VoiceRecorderCard` reports "Voice
note saved locally — pending sync" immediately after a successful recording, never
"uploaded" — and `PendingItemsScreen` shows each voice item's real `sync_status`
(⏳/⬆️/✅/⚠️) in its own "Voice notes" section, same as notes and locations.

## GPS accuracy

`accuracy_meters` (device-reported, when the OS provides one) is stored on the local
row, sent to the backend unchanged, and displayed (`±Nm`) next to the coordinate on
both the Home screen and the location history list. It is treated as descriptive
metadata only in this step — there is no filtering, smoothing, Kalman filter, or
threshold-based rejection of low-accuracy samples. A sample is only ever rejected
for being out of valid coordinate range (an actual data error), never for having a
large accuracy radius. How accuracy should affect confidence/ranking is a decision
for a later step.

## How GuideLocation feeds geographic context

Once a location sample is uploaded, it's a normal row in the backend's
`guide_locations` table — the same table and the same `GET
/api/v1/guides/{guide_id}/context` endpoint from Step 3 pick it up automatically,
with no changes needed on the backend for this step. That endpoint already resolves
context from the guide's *latest* location by `recorded_at` (not insertion order),
which was re-verified end-to-end in this step using out-of-order GPS samples — see
[Tests actually run](#tests-actually-run). This is the concrete version of the
architecture's "location-first" chain:

```
mobile GPS sample -> local_location (SQLite) -> Sync now
    -> GuideLocation row (PostgreSQL/PostGIS)
    -> GET /api/v1/guides/{id}/context uses the latest one by recorded_at
    -> resolves the nearest known place within GEOGRAPHIC_CONTEXT_RADIUS_METERS
```

No route or trek is inferred anywhere in this chain — only "where is this guide,
right now, based on real GPS."

## Configuring the backend URL

Set `EXPO_PUBLIC_API_BASE_URL` (see [`.env.example`](.env.example)) — Expo inlines
`EXPO_PUBLIC_*` vars into the bundle at build/start time. Copy `.env.example` to
`.env` and edit it; `.env` is gitignored, and nothing in this app is a secret either
way.

```
cp .env.example .env
```

- **Web build / iOS simulator, same machine as the backend:** the default,
  `http://127.0.0.1:8000`, works as-is.
- **Physical phone:** `127.0.0.1` resolves to the *phone itself*, not your computer
  — it will never reach the backend. Use your computer's LAN IP instead (find it
  with `ipconfig` on Windows, `ifconfig`/`ip addr` on macOS/Linux), e.g.
  `EXPO_PUBLIC_API_BASE_URL=http://192.168.1.13:8000`. The phone and computer must
  be on the same network, and the backend must be started listening on more than
  loopback, e.g. `uvicorn app.main:app --host 0.0.0.0`.
- **Android emulator:** the emulator's own alias for the host machine's loopback is
  commonly `10.0.2.2` for the standard AVD/Android Studio emulator — this varies by
  emulator, check its docs if that doesn't work.

No code changes are needed for any of the above — only the env var.

## How to manually run a sync

1. Make sure `EXPO_PUBLIC_API_BASE_URL` is set correctly for however you're running
   the app (see above).
2. Create a local guide, a note, record a voice note, and tap "Capture location" a
   few times (all works with the backend stopped).
3. Start the backend (`cd backend && ./.venv/Scripts/python -m uvicorn app.main:app
   --reload`, or with `--host 0.0.0.0` for a physical device).
4. On the Home screen, tap **Sync now**. The button disables and shows a spinner
   while syncing.
5. A truthful summary appears, e.g. "1 note uploaded, 1 voice note uploaded, 3
   locations uploaded." or "2 locations uploaded, 1 item could not be uploaded."
6. Open "View local notes, voice notes, and locations" to see per-item status in
   each section, including the error message for anything that failed.

## What happens when the backend is unavailable

Tapping "Sync now" with no backend reachable:

- The guide-sync request fails with a network error; the result's `guideError` is
  set to a clean, user-facing message (not a raw exception).
- **Nothing else is touched at all** — the flow stops before captures or locations
  are even loaded, so nothing is marked `uploading`, no `sync_attempt_count`
  changes on either table.
- The local guide, every local note, every local voice recording (metadata AND the
  audio file on disk), and every local GPS sample are completely unchanged.
- Everything remains exactly as retryable as before — tapping "Sync now" again once
  the backend is back up picks up right where it left off.

This was verified against the backend actually being stopped, not simulated — see
below.

## Status: what this step does and does not do

Works fully offline, with the backend stopped:

- Create a local guide profile
- Create text notes, stored locally with `sync_status = 'pending'`
- Record voice notes (foreground microphone recording), stored locally — audio file
  on disk + SQLite metadata — with `sync_status = 'pending'`
- Capture the device's current foreground location on demand, stored locally with
  `sync_status = 'pending'`
- View local status for all three (pending / uploading / uploaded / failed, with
  error messages for failures)
- All of the above survives closing and reopening the app

Requires the backend, only when explicitly triggered:

- "Sync now" — creates/resolves the guide, then uploads eligible notes and voice
  recordings (submission + audio, two idempotent requests per recording), then
  eligible locations

Explicitly **not** implemented yet (Step 7 and earlier): continuous/background
location or audio tracking, periodic/scheduled capture, geofencing, route/trek
selection or inference, automatic/background sync, connectivity listeners,
exponential backoff, dead-letter handling, photo capture, audio playback,
audio editing/transcoding, and — critically — **anything AI-related**:
**no Saaras call, no transcription, no LLM call, no structured extraction, no
embeddings, no freshness/staleness calculation, no question generation.** A voice
recording's audio is durably stored on the backend and nothing more; nothing reads
its contents yet. Nothing pretends to work here — see the code comments in
`src/types/models.ts`, `src/location/locationService.ts`,
`src/audio/audioRecordingService.ts`, and `src/sync/syncService.ts`.

**What Step 8 will add** (not started, not scaffolded): the first stage of actually
using the stored audio — Saaras transcription of uploaded voice recordings into
text. Nothing in Step 7 assumes or depends on what that stage will look like.

## Project layout

```
mobile/
  App.tsx                          Root: loads fonts, wraps SafeAreaProvider + SQLiteProvider, renders RootNavigator
  app.json                         expo-sqlite + expo-location + expo-audio (both foreground-only) + expo-font plugin config
  .env.example                     EXPO_PUBLIC_API_BASE_URL documentation/default
  src/
    theme/
      theme.ts                      Design tokens: colors, spacing, radii, type, shadow (Step 15)
      fonts.ts                       useAppFonts() -- loads Bricolage Grotesque + Atkinson Hyperlegible (Step 15)
    components/
      ui/                            Shared design-system primitives (Step 15): Screen, AppHeader, SectionHeader,
                                      Button, Card, Badge, EmptyState, LoadingState, ErrorState, QuickActionTile, TabBar
      VoiceRecorderCard.tsx           Owns the useAudioRecorder/useAudioRecorderState hooks (React's own
                                      constraint), delegates every decision to audioRecordingService
    hooks/
      useLocalActivityCount.ts       Local waiting/failed item count for the Activity tab badge (Step 15)
    db/
      database.ts                   DB name, schema version, migrateDbIfNeeded
      uuid.ts                        generateClientId() -- the one place client ids are generated
    types/models.ts                 LocalGuide, LocalCapture, LocalLocation, LocalAnswer, SyncStatus, CaptureType
    repositories/
      guideRepository.ts             createLocalGuide, getCurrentLocalGuide, updateLocalGuideName, setServerGuideId
      captureRepository.ts           createCapture, createVoiceCapture, listCaptures, getCaptureById,
                                      countCapturesByStatus, listSyncableCaptures, markCaptureUploading/Uploaded/Failed
      locationRepository.ts          createLocation, getLatestLocation, listLocations, countLocationsByStatus,
                                      listSyncableLocations, markLocationUploading/Uploaded/Failed
      answerRepository.ts            createAnswer, getAnswerByQuestionId, listAnswersForGuide, countAnswersByStatus,
                                      listSyncableAnswers, markAnswerUploading/Uploaded/Failed (Step 13)
    location/
      locationService.ts             captureCurrentLocation() -- the only file that calls expo-location
    audio/
      audioRecordingService.ts       ensureMicrophonePermission, startRecording, stopRecording -- the recording
                                      decision logic; RECORDING_OPTIONS/RECORDED_CONTENT_TYPE single source of truth
    api/
      client.ts                      Shared fetch wrapper, API_BASE_URL, ApiError/NetworkError
      guides.ts                      createOrGetGuide()
      submissions.ts                 createOrGetSubmission() -- now note OR voice metadata
      audio.ts                       uploadSubmissionAudio() -- multipart upload, the one deliberate exception
                                      to going through client.ts's apiRequest()
      locations.ts                   createOrGetLocation()
      questions.ts                   listAssignedQuestions(), questionFromWire() (Step 12/13)
      questionAnswers.ts             submitAnswer() -- POST .../questions/{id}/answers (Step 13)
    sync/
      syncService.ts                 syncAll() -- guide, then captures (notes+voice), then locations,
                                      then question answers; syncOneVoiceCapture()'s two-stage idempotent
                                      upload; the in-process sync lock
    screens/
      SetupScreen.tsx                 First-run: create the local guide profile
      HomeScreen.tsx                  Dashboard: adaptive hero, quick actions, voice card, sync status (Step 15)
      CreateNoteScreen.tsx            Text note entry, saved locally
      PendingItemsScreen.tsx          "Activity" tab: notes + voice + locations, failed items surface first
      QuestionsScreen.tsx             Assigned questions grouped by needs-attention/answered (Step 12/13/15)
      AnswerQuestionScreen.tsx        Answer composition for one question, saved locally first (Step 13)
    RootNavigator.tsx                Bottom TabBar (Home/Questions/Activity) + pushed screens (Step 15) --
                                      still no navigation library, plain state-based switching
```

Screens never run SQL, call `fetch`, or call `expo-location`/`expo-audio` directly
— they call the repository functions in `src/repositories/` (the only files that
touch `expo-sqlite`), `captureCurrentLocation()` in `src/location/` (the only file
that touches `expo-location`), `audioRecordingService.ts` in `src/audio/` (the only
file — aside from the one hook-instantiation exception in `VoiceRecorderCard.tsx`
— that touches `expo-audio`), and `syncAll()` in `src/sync/` (the only place that
calls `src/api/`).

## Tests actually run

**TypeScript / build:** `npx tsc --noEmit` — zero errors. Metro (`npx expo start`)
bundled the full app (including `expo-sqlite`, `expo-crypto`, `expo-location`, the
API layer, and the sync engine) for both Android and iOS platforms with zero errors
(799/787 modules).

**No Android/iOS emulator or simulator is available in this environment** (no
`ANDROID_HOME`/`adb`, no iOS simulator on Windows), so the running app — and
specifically the real permission-prompt UI and a real device GPS fix — could not be
exercised on-device. That is stated plainly, not glossed over; no physical GPS
result is claimed anywhere in this document. In its place, the actual
migration/repository/sync SQL and algorithm (copied verbatim from the source files,
not reimplemented from memory) were run against:

- **Node's built-in `node:sqlite`**, a real file-backed database (not `:memory:`),
  with genuine process-level close+reopen between sessions, starting from a
  simulated pre-existing **Step 5** database (a guide with `client_guide_id`, one
  `'uploaded'` note with `client_submission_id` — exactly what a real upgrading
  install would have) to prove the v2→v3 migration:
  - Both the pre-existing guide and note survived completely untouched (same
    client id, same content, same status) after the migration ran.
  - `local_location` was created and immediately usable.
  - A location was persisted, got a `client_location_id` immediately (no backfill
    step needed — this is a brand-new table).
  - The unique index on `client_location_id` is **real, DB-enforced**: a duplicate
    insert was confirmed to throw `UNIQUE constraint failed`, not merely assumed to.
  - `client_location_id` was confirmed unchanged across two separate simulated
    restarts (close, reopen the same file).
  - A full local sync-state round: one location uploaded (`server_location_id`
    stored, cleared from the syncable set), one marked `failed` (error stored,
    stays in the syncable set) — confirmed to survive a subsequent restart still
    `failed` and still retryable, while the uploaded one stayed `uploaded`.
  - **Crash recovery**: a location pushed to `'uploading'` and left there
    (simulating the app being killed mid-request) was confirmed to be picked back
    up by `listSyncableLocations` on the next run, rather than orphaned forever.
  - `getLatestLocation` was confirmed to return the row with the newest
    `recorded_at` among three out-of-order samples, not the most recently inserted
    one.
- **The real running FastAPI backend + real PostgreSQL/PostGIS**, via Node's native
  `fetch` (same request/response shapes as `src/api/`) driving the exact
  `syncAll()` algorithm (guide → notes → locations) end-to-end, in phases:
  1. `setup` — created a local guide, 1 note, and 3 GPS samples with `recorded_at`
     deliberately out of insertion order (the newest-`recorded_at` sample was
     inserted *second*, not last).
  2. `offline` (backend stopped) — sync attempted: `guideSynced: false`, a clean
     network-error message, **zero** notes or locations attempted, guide/note/all
     3 locations completely unchanged, still `pending`, `sync_attempt_count` still
     `0` on every row.
  3. `restart` — reopened the same SQLite file; guide, the note, and all 3 pending
     locations confirmed still present.
  4. `online` (backend started) — seeded a known place (`POST /api/v1/locations`)
     near the newest-`recorded_at` GPS sample, then synced: guide created
     (`server_guide_id` set), the note uploaded, **all 3 locations uploaded**
     (`server_location_id` set on each). Cross-checked directly against
     PostgreSQL with `psql`: exactly 1 guide row, exactly 3 `guide_locations`
     rows with `ST_Y`/`ST_X` on the PostGIS `geog` column matching the stored
     `latitude`/`longitude` exactly, exactly 1 submission row.
  5. `resync` — ran sync a third time: 0 notes and 0 locations attempted (all
     already `uploaded`, correctly excluded), `server_guide_id` unchanged.
     Re-checked PostgreSQL: still exactly 1 guide, 3 locations, 1 submission — no
     duplicates from the repeat sync.
  6. `context` — called the real `GET /api/v1/guides/{id}/context`: it resolved
     using the GPS sample with the newest `recorded_at` (confirmed by exact
     lat/lon/instant match), *not* the one inserted last, and correctly resolved
     `nearest_known_place` to the seeded place (~30m away, well inside the
     500m default radius).

### Step 7 tests

Same two-pronged approach as Step 6 (real `node:sqlite` for the local database,
real backend + PostgreSQL for the network side), since no Android/iOS
emulator/simulator exists in this environment either. **No real microphone
recording was made or claimed** — a controlled binary fixture (arbitrary bytes,
`.m4a` name/content-type, exactly the shape `expo-audio`'s `HIGH_QUALITY` preset
would hand to the upload step) stood in for one, used solely to verify storage,
sync, and idempotency — not audio content itself.

**`node:sqlite`**, starting from a simulated pre-existing **Step 6** database
(schema v3, with a real guide, one `'uploaded'` note, one `'uploaded'` location —
what a real upgrading install would have) to prove the v3→v4 migration, using the
migration SQL copied verbatim from `database.ts`, not reimplemented:

- The pre-existing guide, note, and location all survived completely untouched.
- The four new `local_capture` columns exist and are correctly `NULL` on the
  pre-existing note row (never backfilled — audio-only fields).
- A voice capture row was inserted and correctly stores `capture_type='voice'`,
  `text_content=NULL`, `local_audio_uri`, `audio_duration_millis`,
  `audio_content_type`.
- `client_submission_id` and `client_audio_id` both survived a real close/reopen
  cycle unchanged.
- A pending voice capture survived a simulated restart, still `pending`.
- A voice capture marked `failed` (with a stored error) appeared in the exact
  `listSyncableCaptures` status-filter query — confirmed retryable.
- **Crash recovery**: a voice capture pushed to `'uploading'` and left there
  (simulating a kill mid-request) was confirmed picked back up by the same
  syncable-set query on the next run.
- Creating a brand-new text note after the migration still works unchanged.
- The unique index on `client_audio_id` is **real, DB-enforced**: a duplicate
  insert was confirmed to throw `UNIQUE constraint failed`; multiple `NULL`
  `client_audio_id` values (from ordinary note rows) do **not** collide with each
  other, standard SQL NULL semantics.

**The real running FastAPI backend + real PostgreSQL**, via Node's native
`fetch`/`FormData` reimplementing `syncOneVoiceCapture()` exactly (two requests:
resolve/create submission, then upload audio):

- `setup` → `offline` (unreachable backend, confirmed `NetworkError`, local state
  stayed `pending`→`failed`, the audio fixture untouched) → `restart` (state still
  present) → `online`: guide synced, then the voice capture synced — submission
  created with `submission_type: 'voice'`, `raw_text: null`, and `audio` populated
  (`size_bytes: 3000`, `content_type: 'audio/m4a'`, `duration_seconds: 4.2`,
  exactly matching what was sent). Cross-checked directly against PostgreSQL (not
  just trusting the API's own response): `client_submission_id`,
  `client_audio_id`, `audio_storage_key`, and `audio_size_bytes` all matched.
- `resync`: retrying the identical two-request sync resolved to the **same**
  submission id, and PostgreSQL confirmed exactly one row for that
  `client_submission_id` — no duplicate submission, no duplicate audio.
- **Independence**: a deliberately broken capture (empty audio, rejected by the
  backend with `400`) followed immediately by a good one — the good one still
  synced successfully; one failed item did not block the next.

Directly against the real backend (curl), beyond what the Node E2E script covered:

- `capture_type: 'voice'` with `text_content` supplied → `422` (rejected by the
  schema validator). `capture_type: 'note'` with no `text_content` → `422`. Both
  confirm the "what fields does audio need" schema boundary the spec asked about.
- Invalid audio uploads, each rejected **before** touching storage or the
  database (confirmed: `var/audio_uploads/` file count unchanged after each):
  empty file → `400`; wrong content type (`text/plain`) → `415`; wrong extension
  (`.txt`) → `415`; malformed `client_audio_id` → `400`; a 21 MB file against the
  20 MiB default cap → `413`.
- Attaching audio to a `'note'` submission → `400`. Uploading to a nonexistent
  submission id → `404`.
- **Path traversal**: uploaded a file whose declared name was
  `../../etc/passwd.m4a` — stored safely under a server-generated
  `{random-hex}.m4a` name (confirmed on disk); the malicious string only ever
  appears as inert display metadata in the response's `audio.original_filename`.
- **Idempotent replay**: the exact same `client_audio_id` re-sent after a
  successful upload → `200` with identical data, `var/audio_uploads/` file count
  unchanged (no second file written), submission's `updated_at` unchanged (no
  redundant database write, confirming the replay path returns without touching
  the row at all).
- **Conflict**: a different `client_audio_id` sent to a submission that already
  has audio attached → `409`, file count unchanged (no orphan write on the
  rejected path).
- **Real concurrency, not simulated**: 5 genuinely parallel (`curl ... &` / `wait`)
  identical upload requests (same fresh submission, same `client_audio_id`) against
  a submission that had never had audio attached — exactly one `201`, four `200`s,
  and exactly **one** new file written to disk. This confirms the
  `SELECT ... FOR UPDATE` row lock in `attach_audio_to_submission` actually
  serializes the race, not just in theory.
- **Submission-level idempotency retry**: re-creating a voice submission with the
  same `client_submission_id` after its audio was already attached → `200`,
  returning the exact same submission (including its `audio` block) — the full
  two-stage idempotency loop confirmed end-to-end, not just each stage in
  isolation.

### Idempotency testing results (Steps 5–6, locations)

Run directly against the real backend + PostgreSQL (see `backend/README.md` for the
matching backend-side detail — this repeats the Step 5 guide/submission testing and
adds locations; Step 7's audio idempotency results are in the section above):

- Same `client_location_id` + same payload sent twice → first 201, second 200, same
  server location `id`; `psql` confirmed exactly one row.
- Same `client_location_id` with **different** coordinates → `409 Conflict`,
  original record confirmed unchanged in PostgreSQL.
- **Realistic retry simulation**: two genuinely concurrent (fired in parallel, not
  sequentially) requests with the same brand-new `client_location_id` — one got
  201, the other 200, both resolved to the same server id; `psql` confirmed exactly
  one row despite the race. This exercises the actual `IntegrityError`-catch-and-
  refetch path on the backend, not just the sequential "already exists" check
  (same pattern already proven for guides/submissions in Step 5).

## Manually verifying persistence across a restart

1. Stop the backend (or just don't start it — nothing before "Sync now" calls it).
2. `npx expo start`, open the app.
3. Enter a name on the setup screen, save.
4. From Home, create a note, record and stop a voice note (grant the microphone
   permission prompt when it appears), and tap "Capture location" (grant the
   location permission prompt too).
5. Confirm the note/voice/location counts on Home match, and "View local notes,
   voice notes, and locations" lists them as pending in their respective sections.
6. Fully close the app (not just backgrounding — force-quit it, or reload in Expo
   Go), then reopen it.
7. Confirm the same guide name, the same note, the same voice recording (with its
   duration), and the same captured location are still there, still pending.
8. Start the backend, set `EXPO_PUBLIC_API_BASE_URL` correctly, tap "Sync now."
   Confirm the summary text and that all three sections now show "Uploaded to
   server."

## Architectural decisions relevant to Step 6

- **One sync engine, not two.** GPS locations go through the exact same
  `syncAll()`/in-process lock/crash-recovery machinery as notes — a new,
  independent "location sync" would have duplicated all of that logic and risked
  the two racing each other.
- **`local_location` mirrors `local_capture`'s outbox columns exactly**
  (`client_*_id`, `server_*_id`, `sync_status`, `sync_attempt_count`,
  `last_sync_error`) rather than inventing a different shape — consistency here
  means the sync engine's per-item logic is genuinely parallel, not two subtly
  different implementations.
- **No backfill needed for `local_location`.** Unlike `local_guide`/`local_capture`
  in the v1→v2 migration (which had to backfill ids onto rows that predated the
  column), `local_location` is a brand-new table in v3 — every row has a
  `client_location_id` from the `INSERT` itself, so the migration is just `CREATE
  TABLE` + indexes.
- **Sync order is locations after notes, both after the guide.** Chosen to match
  the task's specified deliberate order; nothing about the design requires this
  order over notes-before-locations, but consistency with the specification is the
  reason, not a technical constraint.
- **The `expo-location` config plugin options were read from the actual installed
  plugin source** (not just the docs) specifically to confirm no background
  permission gets added implicitly — `withBackgroundLocation` and the
  `ACCESS_BACKGROUND_LOCATION`/`FOREGROUND_SERVICE*` Android permissions are only
  applied when `isIosBackgroundLocationEnabled` / `isAndroidBackgroundLocationEnabled`
  are explicitly set, which this app's `app.json` does not do.
- **GPS accuracy is stored and displayed, not filtered.** Rejecting low-accuracy
  samples would be inventing a threshold the backend schema doesn't require and the
  product hasn't specified — that's explicitly deferred to a later ranking/
  confidence step.

## Architectural decisions relevant to Step 7

- **Voice is a `Submission` (`capture_type: 'voice'`), not a new domain concept.**
  `Submission` already means "one thing the guide submitted" — inspecting it first
  (per the task's own instruction) confirmed it cleanly generalizes to audio
  without inventing a parallel "VoiceObservation" entity.
- **Two client ids per voice capture, not one reused twice.** Creating the
  submission and uploading its audio are genuinely separate backend requests that
  can independently succeed or fail and need independently retriable idempotency —
  reusing `client_submission_id` for the audio-attach step would conflate "did we
  create the submission" with "did we attach the audio," which have different
  answers after a partial failure. See [Audio idempotency](#audio-idempotency-step-7).
- **No intermediate local status between "submission created" and "audio
  uploaded."** Both stages of a voice sync are cheap and safe to re-run from
  scratch on every retry (stage 1 is itself idempotent), so there was no need to
  invent a `'submission_created_audio_pending'` status — the existing
  pending/uploading/failed/uploaded state machine, unchanged, is sufficient. Adding
  one would have been exactly the kind of "unnecessarily complicated distributed
  transaction" the task asked to avoid.
- **Audio bytes are never read into a JS string or stored in SQLite.** The local
  `local_audio_uri` column is a file path only; the sync engine hands that URI
  straight to `fetch`/`FormData`, which streams the file from disk. This matters
  for memory: a multi-megabyte recording never sits in a JS string or a SQLite
  BLOB.
- **`useAudioRecorder`'s hook constraint is isolated to one component.** Every
  other service module in this app (`locationService.ts`,
  `audioRecordingService.ts` itself) is plain async functions callable from
  anywhere. `expo-audio`'s recorder can only be instantiated via a React hook —
  `VoiceRecorderCard.tsx` is the one place that constraint leaks into, and even
  there it only holds the hook-provided objects and calls into the service for
  every actual decision.
- **Recordings save to the document directory, not the default cache directory**
  — see [Voice recording](#voice-recording-step-7) above. Read directly from
  `expo-audio`'s own SDK v57 docs (per `mobile/AGENTS.md`'s standing instruction
  to check exact versioned docs before writing Expo code), not assumed from older
  SDK knowledge.
- **Row-level locking (`SELECT ... FOR UPDATE`) for the audio-attach race**,
  where every other idempotency path in this codebase uses the
  IntegrityError-catch-and-refetch pattern instead. The difference: those paths
  guard a single `INSERT` against a unique constraint, where a genuine duplicate
  value naturally can't both commit. The audio-attach race is an `UPDATE` — two
  concurrent requests retrying the *same* `client_audio_id` on the *same* row
  wouldn't violate any uniqueness constraint (it's the same value twice), so a
  real lock was needed to serialize them instead. Verified with 5 real concurrent
  requests — see backend/README.md.
- **Known crash boundaries, stated honestly (not glossed over):**
  - Crash while recording (before `stop()`): no file, no local row — nothing to
    recover, nothing lost that was ever "saved."
  - Crash after `stop()` but before the SQLite insert commits: the audio file
    exists on disk but nothing references it. `VoiceRecorderCard`'s own
    best-effort cleanup only covers the case where the *app* is still running to
    catch the insert's failure — it cannot run after a hard process kill. This
    file is an orphan; nothing in this build detects or reclaims it.
  - Crash after the local row commits, before sync: fully recoverable — the row
    is `pending`, survives restart, syncs normally later.
  - Crash after the server Submission is created but before the audio upload
    completes: fully recoverable — see the Crash recovery paragraph above (the
    row is `'uploading'`, gets retried, submission-creation is idempotent so
    retrying it is safe).
  - Crash after the backend commits the audio upload but before the mobile app
    receives/processes the response: fully recoverable by design — this is
    exactly the case `client_audio_id` idempotency handles (see
    [Audio idempotency](#audio-idempotency-step-7)); the retry finds the audio
    already attached and gets the existing reference back, `200`, no duplicate.
  - On the backend: if the process crashes between writing the file to disk and
    committing the database row update inside `attach_audio_to_submission`, that
    file is orphaned (written, but never referenced by any submission) — see
    `backend/README.md`. Accepted for this step as a storage-cleanliness gap, not
    a correctness issue for any data that IS recorded.

## Transcription status (Step 8)

Step 8 is almost entirely a backend feature (see `backend/README.md` for the
full architecture) — this app's job is still just capture and upload, so the
mobile change here is intentionally small: a manual way to see whether a synced
voice note has been transcribed.

**No `SARVAM_API_KEY` exists anywhere in this app** — not in source, not in
`app.json`, not in any `EXPO_PUBLIC_*` variable, not in `mobile/.env`. This app
only ever calls this repo's own backend; it never talks to Sarvam directly. (This
was an actual finding worth calling out: a Sarvam key was briefly present in
`mobile/.env` during Step 8's setup — moved to `backend/.env`, the correct
gitignored location, before any code was written. It was never an
`EXPO_PUBLIC_*` var, so it was never at risk of being inlined into the JS
bundle, but it didn't belong in the mobile project's environment at all.)

[`src/api/transcriptions.ts`](src/api/transcriptions.ts) adds one function,
`triggerTranscription(submissionId)` — `POST
/api/v1/submissions/{submissionId}/transcribe`. There is no polling and no push
mechanism; nothing here pretends to "live update." In
[`PendingItemsScreen.tsx`](src/screens/PendingItemsScreen.tsx), a voice item that
has actually reached the server (`serverSubmissionId` set — there is nothing to
transcribe before that) gets a **"Transcribe"** button. Tapping it calls the one
endpoint above, which the backend itself resolves into whichever of these is
honestly true and returns as `TranscriptionResponse.status`:

- `pending` / `processing` → shown as "🔤 Transcription pending" / "🔤
  Transcribing…", with a **"Check again"** button (same endpoint, same call —
  the backend decides whether that's a fresh attempt or just a status read; the
  UI never has to know which).
- `completed` → shown as "🔤 Transcribed" with the transcript text in quotes; the
  button disappears (nothing more to check).
- `failed` → shown as "🔤 Transcription failed" with the real `error_message`
  from the backend; **"Check again"** re-appears (retrying is just tapping the
  same button again).

The fetched transcription result is held in that list item's own React state
only — **not written to SQLite**. Storing it locally would mean building a
second local cache with its own staleness/consistency questions (when is a
cached transcript considered stale? does it need its own sync?) for a value the
backend already durably owns and can always be re-fetched from — exactly the
kind of "complicated AI dashboard" this step said to avoid building on mobile.
Backend/API completion was correctly the priority for this step; this UI is
deliberately the minimum that makes the real backend behavior visible and
truthful on-device.

**Tests run for this section**: `npx tsc --noEmit` clean; Metro bundled cleanly
for Android (674 modules) and iOS (676 modules); a Node script reimplementing
`api/transcriptions.ts`'s exact `fromWire()` mapping was run against the real
backend's real response for a completed transcription and matched field-for-
field (`submission_id`→`submissionId`, `language_code`→`languageCode`,
`error_message`→`errorMessage`, etc.) — confirming the wire contract the mobile
code assumes is the contract the backend actually returns, not just assumed
compatible. A real device/emulator was not available (same limitation as every
prior step), so the actual button tap → network round trip → re-render was not
exercised on-device; the wire format and backend behavior it depends on were
verified directly instead.

## Structured extraction status (Step 9)

Step 9 is almost entirely a backend feature too (see `backend/README.md` for
the full architecture: LLM structured extraction, source text resolution,
knowledge-type validation, geographic context attachment). The mobile change
follows the exact same minimal-and-honest discipline as Step 8's transcription
UI — no polling, no auto-trigger, no fake real-time updates.

**No `ANTHROPIC_API_KEY` exists anywhere in this app** — not in source, not in
`app.json`, not in any `EXPO_PUBLIC_*` variable, not in `mobile/.env`. This app
only ever calls this repo's own backend; it never talks to any LLM provider
directly.

[`src/api/extractions.ts`](src/api/extractions.ts) adds one function,
`triggerExtraction(submissionId)` — `POST
/api/v1/submissions/{submissionId}/extract`. In
[`PendingItemsScreen.tsx`](src/screens/PendingItemsScreen.tsx), a shared
`ExtractionBlock` component renders an **"Extract"** button and is shown in two
places, each gated on source text actually being available server-side (never
offered before that, matching Step 9's backend precondition):

- **Notes**: shown once the note has actually synced (`serverSubmissionId`
  set) — a note's text is available for extraction the moment it exists on the
  server.
- **Voice items**: shown only once that item's own transcription state (from
  Step 8's block, same list item) is `completed` — extraction is never offered
  while transcription is missing/pending/processing/failed, since the backend
  would reject it anyway; showing the button earlier would just be a
  UI-level lie about what's actually possible.

Tapping "Extract" calls the one endpoint above, which the backend resolves into
whichever of these is honestly true and returns as `ExtractionResponse.status`:

- `pending` / `processing` → shown as "🧠 Extraction pending" / "🧠
  Extracting…", with a **"Check again"** button (same endpoint, same call —
  the backend decides whether that's a fresh attempt or just a status read).
- `completed` → shown as "🧠 Extracted (N observations)" with each observation's
  `knowledgeType` and raw `value` JSON printed as a plain line (deliberately
  not a polished "AI dashboard" — this step's spec explicitly prioritizes
  backend correctness over mobile presentation); the button disappears.
- `failed` → shown as "🧠 Extraction failed" with the real `errorMessage` from
  the backend; **"Check again"** re-appears.

The fetched extraction result is held in that list item's own React state
only — **not written to SQLite** — for the identical reasoning as Step 8's
transcription result: the backend already durably owns it and can always be
re-fetched, so a second local cache would just add staleness questions for no
benefit.

**Tests run for this section**: `npx tsc --noEmit` clean (verified after
adding `src/api/extractions.ts` and the `ExtractionBlock`/`formatExtractionStatus`
additions to `PendingItemsScreen.tsx`). `ExtractionResponse`'s `fromWire()`
mapping was checked by hand against a real backend extraction response
(`id`, `submission_id`→`submissionId`, `status`, `error_message`→
`errorMessage`, `observations[].knowledge_type`→`knowledgeType`, `value`,
`confidence`, `evidence` — all present and correctly named in the real
payload). A real device/emulator was not available (same limitation as every
prior step), so the actual button tap → network round trip → re-render was not
exercised on-device.

## Assigned questions (Step 12)

Step 12 is almost entirely a backend feature (see `backend/README.md` for the
full architecture: LLM question generation, idempotency, revalidation,
assignment). The mobile app never generates a question — that's an explicit,
server/backend-triggered action in this step (`POST /api/v1/questions`,
called from `curl`/a future admin tool, not from this app). This app's role is
strictly read-only: display whatever the server has already assigned.

**No `ANTHROPIC_API_KEY` exists anywhere in this app** — same guarantee as
Step 9, unchanged: not in source, not in `app.json`, not in any
`EXPO_PUBLIC_*` variable, not in `mobile/.env`.

[`src/api/questions.ts`](src/api/questions.ts) adds one function,
`listAssignedQuestions(guideId)` — `GET /api/v1/guides/{guideId}/questions`.
[`src/screens/QuestionsScreen.tsx`](src/screens/QuestionsScreen.tsx) is a new
screen (reached from a "View assigned questions" button on `HomeScreen`)
showing that list with a manual **"Refresh"** button — no polling, no push,
no WebSocket, matching Step 8/9's discipline exactly. Gated on
`guide.serverGuideId` being set (a question can only be fetched for a guide
that has actually synced to the server; if it hasn't yet, the screen says so
instead of attempting the call).

**Questions are deliberately NOT part of `local_capture`/the outbox sync
engine, and are not written to SQLite at all.** This is a real architectural
distinction, not an oversight: everything in `local_capture` (notes, voice
recordings) is data the guide *creates* on this device and that flows
*outward* to the server via the existing sync engine. A question is the
opposite direction — a server-originated work item hander *to* the guide —
and has no `client_*_id`, no `sync_status`, and nothing to retry-upload; it
doesn't fit the outbox's shape or purpose at all. Holding it only in
component state (re-fetched on demand) avoids inventing a second, parallel
local-storage concept for data the backend already durably owns and can
always be re-fetched — the same reasoning already applied to Step 8/9's
transcription/extraction results.

**Tests run for this section**: `npx tsc --noEmit` clean after adding
`src/api/questions.ts`, `src/screens/QuestionsScreen.tsx`, and the
`onViewQuestions` wiring through `HomeScreen.tsx`/`RootNavigator.tsx`.
`Question`'s `fromWire()` mapping was checked by hand against real backend
`POST /api/v1/questions` responses captured during backend testing (`id`,
`knowledge_type`→`knowledgeType`, `display_name`→`displayName`, `gap_state`→
`gapState`, `target_latitude`/`target_longitude`, `nearest_known_place_name`/
`_distance_meters`, `safety_critical`→`safetyCritical`, `default_priority`→
`defaultPriority`, `staleness_severity_hours`→`stalenessSeverityHours`,
`gap_rank`→`gapRank`, `question_text`→`questionText`, `short_context`→
`shortContext`, `status`, `error_message`→`errorMessage`, and the nested
`assignment` object's `guide_id`→`guideId`/`guide_name`→`guideName`/
`assigned_at`→`assignedAt`/`answered_at`→`answeredAt` — all present and
correctly named in the real payload). A real device/emulator was not
available (same limitation as every prior step), so the actual button tap →
network round trip → re-render was not exercised on-device.

## Knowledge aging (Step 14)

The backend added a new `'aging'` knowledge/gap state, between `'missing'`
and `'stale'` (see `backend/README.md`'s Step 14 section for the full
semantics). Inspected every mobile usage of `gap_state`/`gapState` first:
it appears ONLY in `src/api/questions.ts`'s type definitions — neither
`QuestionsScreen.tsx` nor `AnswerQuestionScreen.tsx` branches on it anywhere
(both just display whatever `questionText`/`displayName`/`safetyCritical`
the server sends, which is already state-agnostic — the LLM's own wording
already adapts per state on the backend, see Part G of Step 14). So the
**entire** mobile change for this step is widening the TypeScript type:
`Question['gapState']` is now `'missing' | 'aging' | 'stale'` (a new
exported `GapState` type) instead of `'missing' | 'stale'`. No new screens,
no new UI copy — the "needs a recent update" tone Part I asks for is
produced server-side by the LLM prompt and already flows through verbatim
via the existing `question_text` field this app already renders as-is.

**Tests run**: `npx tsc --noEmit` — clean. No real device/emulator was
available (same limitation as every prior step); since no UI logic branches
on `gapState`, there was no on-device behavior to exercise beyond the
type-check.

## Guide answers (Step 13)

Closes the loop: a guide can now open an assigned question, answer it
offline-first, and have that answer sync to the backend. Same architecture
discipline as every prior sync-eligible feature — local-first, one shared
sync engine, no new lock, no new local-storage concept beyond one new table.

**No `ANTHROPIC_API_KEY` here either** — answering a question never calls an
LLM at all (backend-side or otherwise); see `backend/README.md`'s Step 13
section. This app never talks to Anthropic, directly or indirectly.

### Local schema (`local_answer`, DATABASE_VERSION 4 → 5)

A new table, added the same additive way as every prior migration step in
[`src/db/database.ts`](src/db/database.ts) — `CREATE TABLE IF NOT EXISTS` /
`CREATE INDEX IF NOT EXISTS` only, no `ALTER`/`DROP` on any existing table, so
every pre-existing `local_guide`/`local_capture`/`local_location` row is
untouched. Two DB-enforced `UNIQUE` indexes:

- `client_answer_id` — the idempotency key sent to the backend (mirrors
  `client_submission_id`/`client_location_id`).
- `server_question_id` — **at most one local answer per question**, ever.
  This directly enforces this step's "one guide answer must not silently
  overwrite another" requirement at the local layer too, not just the
  backend's: `createAnswer()` cannot be called twice for the same question
  even before either attempt has synced.

### The answer flow

1. Guide taps a question in `QuestionsScreen` → navigates to
   `AnswerQuestionScreen` (a new screen reached via a `selectedQuestion`
   piece of state in `RootNavigator.tsx` — no navigation library added, same
   pattern as every other screen transition in this app).
2. If a local answer already exists for this question (or the server already
   shows the assignment `completed` — e.g. answered from a different
   device), the screen shows it **read-only** instead of a compose form —
   there is no edit/re-answer flow in this step, matching the backend's
   one-answer-per-assignment design.
3. Otherwise, the guide types an answer and taps "Save answer locally" —
   `answerRepository.createAnswer()` inserts one row with `sync_status =
   'pending'` and returns **immediately**. No network call is made at any
   point in this screen — answering works with the backend fully
   unreachable.
4. The answer now appears in `syncService.listSyncableAnswers()`'s scope and
   uploads on the next "Sync now" tap, exactly like a note or a location.

### Sync

`syncService.ts` gained a fourth, independent stage — `syncOneAnswer()` —
processed after captures and locations in `performSync()`. Same guarantees
as every existing stage:

- **Independent failure**: one answer's sync failure (e.g. a `409`/`403` from
  the backend) is caught, recorded via `markAnswerFailed`, and does not abort
  captures/locations or other answers already queued.
- **Crash recovery**: `'uploading'` is in `listSyncableAnswers`'s eligible
  statuses for the same reason as captures/locations — the in-process sync
  lock (`isSyncing()`/`syncInFlight`) does not survive an app kill, so an
  answer stuck `'uploading'` from a killed session is retried on the next
  sync, never orphaned.
- **No duplicate backend answers on re-sync**: once `markAnswerUploaded` sets
  `sync_status = 'uploaded'`, the row drops out of the syncable set entirely
  — a later `syncAll()` never re-sends it. Combined with the backend's own
  `client_answer_id` idempotency, a re-send (if it ever did happen) would
  still resolve to the same server answer, not a duplicate — belt and
  suspenders, same philosophy as note/location sync.
- **No separate sync lock** — reuses the exact same `syncInFlight`
  module-level promise every other stage already shares.

A `409` (already answered) or `403` (wrong guide) from the backend is not
specially distinguished from a transient network failure — it becomes a
`'failed'` local row with the server's message, shown to the guide, and
remains tap-to-retry-eligible via the next "Sync now," exactly like every
other kind of sync failure in this app. Retrying a genuine `409`/`403` won't
succeed, but that mirrors how `AudioConflictError` is already handled for
voice captures — no new special-casing was introduced for this step.

### UI: truthful, merged status

`QuestionsScreen` now fetches **both** the server's assigned-questions list
and this device's local answers on every refresh, and merges them per
question (`describeProgress()`) into one of five truthful states — never
"answered" merely because local text exists:

- **Waiting for your answer** — no local answer, assignment not `completed`.
- **Answered locally — waiting to send** — local `sync_status: 'pending'`.
- **Sending your answer…** — local `sync_status: 'uploading'`.
- **Answer saved locally — send failed, will retry** — local `sync_status:
  'failed'`.
- **Answered** — either the local answer's `sync_status` is `'uploaded'`, OR
  the server's own `assignment.status` is already `'completed'` (covers an
  answer synced from a different device, where this device has no local row
  at all).

### Tests run for this section

- `npx tsc --noEmit` — clean after every file in this step (`answerRepository.ts`,
  `questionAnswers.ts`, `AnswerQuestionScreen.tsx`, the `QuestionsScreen.tsx`/
  `RootNavigator.tsx`/`HomeScreen.tsx`/`syncService.ts` edits, and the new
  `LocalAnswer`/`AnswerSyncSummary`/`QuestionAnswer` types).
- **Real SQLite migration/persistence test** (no emulator/device needed for
  this — plain file-backed SQLite is the same engine `expo-sqlite` binds to):
  ran the LITERAL SQL from `database.ts`'s v0→v4 steps to build a realistic
  pre-Step-13 database with real pre-existing guide/note/location rows, then
  applied the new v4→v5 block and verified — all against a real `.db` file,
  not mocked:
  - Pre-existing guide/note/location rows survive byte-for-byte (row counts
    and content both checked).
  - `PRAGMA user_version` correctly becomes `5`.
  - An answer can be inserted with **no backend running** (the test never
    opens a network connection at all).
  - The answer survives closing and reopening the database connection
    (simulated app restart) — `client_answer_id` unchanged.
  - A duplicate `client_answer_id` is rejected by the DB
    (`sqlite3.IntegrityError`, `UNIQUE constraint failed`).
  - A second local answer for the same `server_question_id` is rejected by
    the DB (same mechanism) — enforces "one answer per question" locally.
  - A row manually set to `'uploading'` (simulating a killed app mid-sync)
    remains in the syncable set — confirmed retryable.
  - A row marked `'uploaded'` (simulating a successful sync) is excluded
    from the syncable set — confirmed a re-sync would not re-upload it.
  - Pre-existing tables' row counts re-checked as unchanged at the very end.
- **Real backend integration** (see `backend/README.md`'s Step 13 section for
  the full command-by-command results): every case above — first
  submission, idempotent replay, conflict, already-answered, 3-way real
  concurrency, ownership rejection, cancelled-assignment rejection,
  no-assignment rejection, unknown-question 404, blank-answer 422, and the
  real extraction pipeline producing real observations from a real answer —
  was exercised against the real FastAPI + PostgreSQL backend from this
  step's own testing pass, using the same wire format this app's
  `questionAnswers.ts`/`questions.ts` send and parse.

### What could not be tested

No real Android/iOS emulator or physical device was available in this
environment (same limitation noted in every prior mobile step) — so the
actual tap → `AnswerQuestionScreen` → "Save answer locally" → return to
`QuestionsScreen` → "Sync now" → observe "Answered" UI flow was not exercised
end-to-end on-device. `questionFromWire()`'s new `answer` field mapping was
checked by hand against a real captured `POST .../answers` response
(`id`, `question_id`→`questionId`, `assignment_id`→`assignmentId`,
`guide_id`→`guideId`, `answer_text`→`answerText`, `submission_id`→
`submissionId`, `answered_at`→`answeredAt` — all present and correctly named).

## UI/UX redesign (Step 15)

A visual and information-architecture redesign of every screen — no backend
contract changes, no business-logic changes. Every repository/API/sync
function is byte-identical to before this step except two additive,
purely-presentational helpers noted below; only JSX and styling changed.

### Design system (`src/theme/`, `src/components/ui/`)

- `theme/theme.ts` — the single source of truth for color, spacing, radius,
  and type. Palette (`ink`/`marigold`/`paper`/`ok`/`fix`) is inspired by the
  attached reference design's own palette, re-picked for this app rather
  than pixel-matched.
- `theme/fonts.ts` — `useAppFonts()`, loading **Bricolage Grotesque**
  (headings) and **Atkinson Hyperlegible** (body) via
  `@expo-google-fonts/*`. Atkinson Hyperlegible was designed specifically
  for legibility in low-vision and high-glare conditions — directly relevant
  to a guide reading a phone outdoors in bright sun, not a cosmetic choice.
  `App.tsx` blocks rendering `RootNavigator` until both font sets resolve,
  so no screen ever flashes system-font text.
- `components/ui/` — the small, deliberately non-exhaustive set of
  primitives every screen is built from: `Screen`, `AppHeader`,
  `SectionHeader`, `Button` (primary/secondary/ghost/danger),  `Card`
  (raised/flat/outline), `Badge` (the one status-communication primitive —
  every sync/transcription/extraction/question/assignment state renders
  through this), `EmptyState`, `LoadingState`, `ErrorState`,
  `QuickActionTile`, `TabBar`. No screen hand-rolls a status pill, a
  loading spinner, or a card shadow anymore.

### Dependencies added

All installed via `npx expo install` (the Expo-recommended, SDK-version-
matched method — never a manually-guessed version):

- `@expo/vector-icons` — replaces emoji-as-UI-language (⚠️/✅/🎙️) with real,
  consistent iconography (Part C explicitly asks to avoid excessive emoji).
- `expo-font`, `@expo-google-fonts/bricolage-grotesque`,
  `@expo-google-fonts/atkinson-hyperlegible` — the two typefaces above.
  Font files ship as bundled assets inside the npm packages themselves; no
  runtime network fetch.
- `react-native-safe-area-context` — proper safe-area insets (`Screen.tsx`,
  `TabBar.tsx`) instead of the previous hard-coded `paddingTop: 64`, which
  was exactly the "layout that only works on one device size" anti-pattern
  Part L warns against.

No navigation library was added (see Navigation below) and no large UI
framework was added — every primitive above is a plain React Native
component using the theme tokens.

### Navigation changes

`RootNavigator.tsx` now renders a persistent bottom `TabBar` (Home /
Questions / Activity) around the three top-level screens, plus a lightweight
"pushed screen" concept (`CreateNoteScreen`, `AnswerQuestionScreen`) that
takes over the full screen without the tab bar — a stack-push *feel* built
from plain `useState`, not a routing library, extending the exact
state-based pattern this app has used since Step 4. `SetupScreen` remains
its own pre-tab gate, unchanged. Returning to a tab root (or closing a
pushed screen) bumps a `refreshKey` that every tab screen already re-reads
on — the same "remount doubles as refresh" pattern established in Step 4,
now made explicit and reusable instead of ad hoc per screen.

The Questions tab shows a small badge (count of assigned-but-not-completed
questions) sourced from `QuestionsScreen`'s own existing fetch — lifted up
via an `onCountChange` callback rather than a second, duplicate network
call. The Activity tab shows a badge (local items waiting to sync or
failed) computed via a new `useLocalActivityCount` hook, which in turn
needed one small additive repository function,
`answerRepository.countAnswersByStatus` — mirroring the pre-existing
`countCapturesByStatus`/`countLocationsByStatus` exactly, the only
non-presentational code added in this step.

### Screens redesigned

- **Home** — now an actual dashboard: a greeting header, an *adaptive* hero
  card (real data only — "N questions need your input" if any exist, else
  "N items waiting to sync" if any, else a calm "You're all caught up" —
  never a fixed or fabricated message), a "Record an update" quick-actions
  row (Add note / Capture location) plus the restyled voice recorder card,
  a "Last known location" card, a Sync card with real status badges, and a
  link into Activity. Answers "who am I / what should I do next / is my
  data safe / what's waiting" per Part F, from real state at every step.
- **Questions** — cards grouped into "Needs your input" and "Answered"
  (server truth, `assignment.status`), each showing a truthful merged
  local+server progress badge (unchanged logic from Step 13/14, only its
  presentation changed) and, only where it helps convey urgency, a plain-
  language gap-state badge ("No report yet" / "Getting old" / "Update
  needed") — never the raw `missing`/`aging`/`stale` strings or any ranking
  internals. Native pull-to-refresh in addition to the tab switch itself
  triggering a refresh.
- **Answer a question** — the question is the visually dominant element;
  compose mode and the two read-only modes (answered locally / answered
  from another device) are clearly distinct cards, each with its own
  explicit sync-status badge.
- **Activity** (`PendingItemsScreen.tsx` — kept its filename, its user-
  facing title is "Activity") — notes/voice/locations grouped by type as
  before, but within each group failed items sort first (progressive
  disclosure per Part I) instead of a second duplicate "needs attention"
  list to keep in sync. Nested transcription/extraction actions are
  unchanged logic, restyled into a quieter nested block so completed
  information doesn't visually compete with actionable buttons.
- **New note** / **Setup** — re-skinned onto the same primitives; identical
  behavior.
- **Voice recorder card** — restyled in place (own file, still the only
  component instantiating `useAudioRecorder`): idle state is a calm
  "Tap to record" card; recording state inverts to a dark, high-contrast
  card with a large timer, matching the reference's own recording-state
  treatment.

### How existing functionality was preserved

Every repository, API client, and the sync engine are untouched (one
additive function, noted above). Every screen's data-fetching/mutation call
sites are the same calls as before this step — `createCapture`,
`createVoiceCapture`, `captureCurrentLocation`/`createLocation`,
`listAssignedQuestions`, `createAnswer`/`getAnswerByQuestionId`,
`triggerTranscription`/`triggerExtraction`, `syncAll` — only their
surrounding JSX changed. The truthful state-machine distinctions from Step
14's Part J (saved locally vs. waiting vs. syncing vs. failed vs. uploaded
vs. each AI-processing status vs. each question/assignment status) are
preserved exactly; `Badge` only ever renders a label already derived by the
existing logic, never invents one.

### Tests run

- `npx tsc --noEmit` — clean.
- `npx tsc --noEmit --noUnusedLocals --noUnusedParameters` (a one-off
  stricter pass, not a permanent tsconfig change) — caught one genuinely
  unused import (`ApiError`/`NetworkError` in `HomeScreen.tsx`), fixed, then
  clean.
- `npx expo export --platform ios --platform android` — **both platforms
  bundled successfully** (813 modules iOS, 811 Android, ~2.2MB Hermes
  bytecode each, zero bundler errors) — this is real verification that
  every new screen, the font loading, and the new native dependencies
  (`react-native-safe-area-context`, `@expo/vector-icons`) actually resolve
  and bundle correctly, beyond what type-checking alone confirms.

### What could not be tested

No real Android/iOS emulator or physical device was available in this
environment (same limitation as every prior mobile step) — the redesigned
screens were not tapped through on a device or simulator. No screenshot or
visual rendering could be produced or verified here either. This is stated
honestly rather than claimed.

### Known limitations / intentional decisions

- `@expo/vector-icons` bundles all ~30 of its vendor icon-font families as
  static assets regardless of which set is actually imported (only
  `Ionicons` is used here) — a known characteristic of the package, not a
  bug; ejecting or adding custom font-subsetting tooling to trim this was
  judged out of scope for a UI redesign step.
- The bottom tab bar's Activity badge and Home's sync counts are each
  computed by independent local SQLite reads (not a shared cache/store) —
  they can be momentarily inconsistent with each other by a query or two,
  never with the database itself. No global state store was introduced;
  this matches the app's existing "no shared client-side store, repositories
  are the source of truth" architecture.
- No screenshots/visual QA were possible without a device; all "modern,
  polished" claims in this summary describe the code and design tokens
  actually written, not an observed rendering.

## Explore (Step 16)

A new bottom tab: **Home · Explore · Questions · Activity**.

### What Explore is, and how it differs from Questions

> Explore helps us discover knowledge **before** we know we need it.
> Questions helps us deliberately collect knowledge **once we know** we're missing it.

|  | **Explore** | **Questions** |
|---|---|---|
| Feel | Invitation — open, contextual, discovery-led | Obligation — an operational work queue |
| Prompts come from | The device, built from real backend context | The server, generated from a ranked gap |
| Persisted server-side? | No | Yes (`Question` + `QuestionAssignment`) |
| Assigned to you? | No — always available | Yes |
| Saves as | `explore` capture → `explore` submission | `local_answer` → `answer` submission |

They are deliberately **not** mixed. Explore prompts never enter the Questions
queue, and assigned questions never appear in Explore.

### Home is now a dashboard, not a queue

The dominant "N questions for you" hero card is **gone** from Home. Home's hero
now reports *this device's* state (anything waiting to send?), and Questions is
reachable via a compact shortcut showing a truthful count — or no count at all
when it hasn't resolved yet, rather than a fabricated placeholder.

### Offline-first flow

```
Explore prompt -> compose (text, optional photo) -> saved to SQLite ('pending')
       -> app can be closed / offline for days
       -> "Sync now" on Home
       -> POST /submissions (capture_type 'explore')      [idempotent: clientSubmissionId]
       -> POST /submissions/{id}/photo, only if attached  [idempotent: clientPhotoId]
       -> marked 'uploaded'
       -> (explicit) extraction -> Observations -> knowledge lifecycle
```

Same single sync engine (`src/sync/syncService.ts`) as notes, voice, locations,
and answers — **no parallel sync system**. `syncOneExploreCapture` mirrors
`syncOneVoiceCapture`'s two-stage, both-idempotent shape, with one difference:
the photo is genuinely optional (a voice capture without audio is meaningless;
a text-only discovery is complete).

Crash/restart recovery is inherited unchanged: `'uploading'` is in
`SYNCABLE_STATUSES`, so a capture stranded by an app kill is retried rather
than orphaned.

### Text is always required

Even with a photo attached. The backend turns **text** into observations and
does no image understanding, so a photo-only contribution could never become
knowledge. The composer says this plainly instead of accepting a silent dead
end.

### Prompt generation — on-device, never fabricated

Built in `src/explore/explorePrompts.ts` from two existing endpoints
(`/guides/{id}/context`, `/guides/{id}/knowledge-state`). No new backend
surface, no persistence, no LLM call, no polling.

The governing honesty rule: **a prompt may only name a place if the backend
actually resolved one.** With no location, copy falls back to place-neutral
wording and the hero says so — Explore never claims "you're near X" on a guess.

The deck mixes:
- **Grounded prompts** (max 2) built from real gaps the backend reported, each
  showing *why* it's being asked ("The last weather report here is out of
  date"). Ordered safety-first, then missing → stale → aging, matching the
  backend's own urgency ordering.
- **Open discovery prompts** — photo moments, local stories, cultural context,
  good finds — rotated by a seed derived from the day and ~1km-rounded
  coordinates, so the deck feels alive as you move but is stable while you
  stand still (pull-to-refresh is not a slot machine).
- **"Share anything"** — a permanent, always-first affordance. A guide must
  never have to wait for the right card to appear to report something.

### Every state is truthful

| Situation | What Explore shows |
|---|---|
| Profile not synced | "Profile not synced yet" — you can still save; it sends later |
| No location captured | Place-neutral prompts + an honest nudge, never a guessed place |
| Context loaded | Real place name, real distance, real location age |
| Fetch failed | `ErrorState` with retry — never a silently empty deck |
| Items awaiting sync | "N discovery items waiting to send", from local SQLite (works offline) |

Loading state is released in a `finally` on every path, so it can never outlive
the work it describes.

### Photos

`expo-image-picker` (SDK-pinned `~57.0.14`), with permission strings declared in
`app.json`. Following the existing microphone/location discipline: permission is
requested **only** from an explicit user action, denial and cancellation are
distinct outcomes, and nothing is fabricated on failure.

The picked image is **copied into the app's document directory** before use.
That matters: the OS picker URI points at a cache location that can be reclaimed
at any time — exactly the class of bug that made voice notes silently unsendable
earlier in this project. Copying means the file is still there when sync runs
days later, after a restart. Images are downscaled/recompressed
(`quality: 0.6`, EXIF stripped) to stay well inside the backend's 10 MiB cap.

Upload uses `expo-file-system`'s native `File#upload()` — the same proven path
as audio, deliberately reusing that hard-won fix rather than rediscovering the
RN `fetch`+`FormData` failure.

### Local schema (v5 → v6)

Five additive nullable columns on `local_capture`: `local_photo_uri`,
`client_photo_id`, `photo_content_type`, `explore_prompt_id`,
`explore_prompt_title`; plus `ux_local_capture_client_photo_id`.

**No backfill** — a pre-Step-16 capture genuinely has no photo. The unique index
is safe to create immediately precisely *because* every existing row is NULL,
and SQLite treats NULLs as distinct (contrast the v1→v2 step, which had to
backfill ids first).

`explore_prompt_*` are **local-only provenance** — the backend does not model
prompts. They exist so Activity can honestly show what was asked.

### Idempotency

Three distinct client-generated ids per Explore contribution with a photo:
`clientSubmissionId` (the submission), `clientPhotoId` (the photo attachment).
Both are generated once and never regenerated, so a retry after a lost response
resolves to the same server state instead of duplicating. `clientPhotoId` is
`NULL` when no photo is attached — that null is what tells the sync engine there
is no second upload step.

### Deliberately NOT implemented

Editing or deleting a saved contribution, multiple photos per contribution,
voice-based Explore contributions (voice capture remains on Home), viewing
already-uploaded photos back from the server, offline map/tiles, background
sync, notifications, or any automatic extraction trigger.
