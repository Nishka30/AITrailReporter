/**
 * Lifecycle of a locally captured item on its way to the backend. Step 4 only ever
 * produces 'pending' — the remaining states describe the future outbox/sync engine
 * (Step 5+) and are defined now so storage and UI don't need to change shape later.
 */
export type SyncStatus =
  | 'pending'
  | 'uploading'
  | 'uploaded'
  | 'processing'
  | 'synced'
  | 'failed'
  | 'dead_letter';

/**
 * What kind of capture this is.
 *
 * - 'note'    — an unprompted text field report (Step 4)
 * - 'voice'   — an audio recording (Step 7)
 * - 'explore' — a proactive Explore-tab discovery contribution (Step 16):
 *               always carries text, and OPTIONALLY a photo attached to the
 *               same submission. It is its own capture type rather than a flag
 *               on 'note' because the provenance genuinely differs (a note is
 *               unprompted; an Explore contribution answers a discovery prompt
 *               the app surfaced) — and the backend models it the same way, as
 *               submission_type 'explore'.
 * - 'memory'  — a contribution not tied to a live moment or verified place: an
 *               old photo, a recalled story. Structurally identical to
 *               'explore' (same composer, same optional text/photo/voice) —
 *               the entire difference is that its location/date provenance is
 *               determined rather than assumed to be "here and now" (see the
 *               location.../occurredAt... fields on LocalCapture below, and
 *               src/location/photoLocationResolver.ts).
 * - 'photo'/'mixed' — reserved, still not produced by any flow. A photo is
 *               attached to an 'explore'/'memory' capture, NOT stored as a
 *               standalone 'photo' capture, so that a contribution is always
 *               one submission with one extractable text body.
 */
export type CaptureType = 'note' | 'voice' | 'explore' | 'memory' | 'photo' | 'mixed';

/**
 * How a capture's latitude/longitude came to be, in decreasing order of
 * trustworthiness. Mirrors the backend's SUBMISSION_LOCATION_SOURCES exactly
 * (app/db/models/submission.py) — kept as the same set of string values on
 * both sides so nothing is translated or re-interpreted crossing the wire.
 */
export type LocationSource =
  | 'photo_exif'
  | 'gps_live'
  | 'historical_inferred'
  | 'user_selected'
  | 'approximate'
  | 'unknown';

/** Mirrors the backend's DATE_PRECISIONS exactly. */
export type DatePrecision = 'exact' | 'month' | 'year' | 'approximate' | 'unknown';

/** Mirrors the backend's DATE_SOURCES exactly. */
export type DateSource = 'device' | 'exif' | 'user_entered' | 'inferred' | 'unknown';

/**
 * Which of the two question sources a local answer belongs to (Step 18).
 * See LocalAnswer.questionKind for what each one syncs to.
 */
export type QuestionKind = 'dynamic' | 'popular';

/**
 * A guide profile stored on this device.
 *
 * `id` is the local SQLite row id — it is NOT a backend identifier and must never be
 * sent to the API as a guide id.
 *
 * `clientGuideId` is a stable UUID generated once, on this device, when the profile
 * is first created (see `src/db/uuid.ts`) — it is what makes `POST /api/v1/guides`
 * idempotent, and it must NEVER be regenerated for an existing row.
 *
 * `serverGuideId` starts out null and is only populated once the sync engine has
 * successfully created (or resolved) this guide on the backend via
 * `POST /api/v1/guides`. Until then, this profile has no representation on the
 * server at all.
 */
export interface LocalGuide {
  id: number;
  clientGuideId: string;
  serverGuideId: string | null;
  name: string;
  phoneNumber: string | null;
  /**
   * Profile fields (Step 17). This device's guide profile IS the app's user
   * identity — there is deliberately no second "user" model. `name` and
   * `phoneNumber` above already exist on the backend Guide and are pushed to
   * it; the two fields below are LOCAL-ONLY and never leave the device.
   *
   * `aboutText` is the optional "About you" note. It is personal metadata, not
   * field knowledge: it is never sent to the backend, never becomes an
   * Observation, never affects knowledge freshness, and is never included in
   * any LLM or transcription request. See mobile/README.md's privacy section.
   *
   * `localPhotoUri` is an on-device file path for the profile picture (the
   * image bytes are never stored in SQLite, same rule as audio and Explore
   * photos). There is no backend endpoint for guide avatars, so this is local
   * to this install by design rather than half-synced.
   */
  aboutText: string | null;
  localPhotoUri: string | null;
  /**
   * True when `name`/`phoneNumber` have been edited locally and that change has
   * not yet been pushed to the backend. Set by profile edits, cleared once the
   * sync engine has confirmed the server accepted them — the same
   * "local truth first, confirmed later" discipline every other outbox record
   * in this app uses. Always false while `serverGuideId` is null, because
   * guide creation sends the current values anyway.
   */
  profileDirty: boolean;
  createdAt: string;
  updatedAt: string;
}

/**
 * A capture (a text note or, since Step 7, a voice recording) recorded on this
 * device.
 *
 * `id` is a local SQLite row id, not a backend submission id. `localGuideId`
 * references `LocalGuide.id` (also local-only).
 *
 * `clientSubmissionId` is a stable UUID generated once, when the capture is first
 * created — it is what makes `POST /api/v1/submissions` idempotent, and it must
 * NEVER be regenerated. `serverSubmissionId` is populated once the backend has
 * confirmed receipt (`syncStatus` becomes `'uploaded'`). `syncAttemptCount` and
 * `lastSyncError` are sync bookkeeping only — they don't affect what's shown as the
 * capture's content.
 *
 * The `audio*`/`localAudioUri`/`clientAudioId` fields are only ever set for
 * `captureType === 'voice'` rows — always null for 'note' rows.
 * `localAudioUri` is the on-device file path (the audio bytes themselves are
 * never stored in SQLite — see mobile/README.md). `clientAudioId` is a SECOND,
 * distinct stable id from `clientSubmissionId`: it makes the audio *upload* step
 * independently idempotent, since creating the submission and uploading its audio
 * are two separate backend requests during sync (see src/sync/syncService.ts).
 * `audioDurationMillis` is whatever expo-audio actually reported — never a
 * fabricated value — and may be null if unavailable.
 */
export interface LocalCapture {
  id: number;
  localGuideId: number;
  clientSubmissionId: string;
  serverSubmissionId: string | null;
  captureType: CaptureType;
  textContent: string | null;
  localAudioUri: string | null;
  clientAudioId: string | null;
  audioDurationMillis: number | null;
  audioContentType: string | null;
  /**
   * Photo fields (Step 16) — only ever set for `captureType === 'explore'`
   * rows, and even then only when the guide actually attached a photo (an
   * Explore contribution can be text-only). Always null for note/voice.
   *
   * `localPhotoUri` is the on-device file path; the image bytes are never
   * stored in SQLite, exactly like audio. `clientPhotoId` is a THIRD distinct
   * stable id (alongside clientSubmissionId and clientAudioId) making the
   * photo upload step independently idempotent, since it is its own backend
   * request during sync.
   */
  localPhotoUri: string | null;
  clientPhotoId: string | null;
  photoContentType: string | null;
  /**
   * NOTE (Step 17): the audio fields above are no longer voice-only. An
   * 'explore' capture may now populate the SAME `localAudioUri` /
   * `clientAudioId` / `audioDurationMillis` / `audioContentType` columns to
   * carry a voice note alongside its optional text and optional photo. No new
   * columns were added for this — reusing them keeps one upload path, one
   * idempotency key, and one set of sync rules for all recorded audio in the
   * app, rather than a parallel Explore-only audio system.
   *
   * So the honest read of these fields is "this capture has audio", not "this
   * capture is a voice note". Use `captureType` to distinguish the two.
   */
  /**
   * Which Explore prompt this contribution answered. Local-only provenance —
   * the backend does not model prompts (see mobile/README.md). Null for every
   * non-Explore capture, and also for a free-form "share anything" Explore
   * contribution that wasn't answering a specific prompt.
   */
  explorePromptId: string | null;
  explorePromptTitle: string | null;
  /**
   * Which backend-researched place question this contribution answers — the
   * "you're here right now" invitations tied to a known Location. UNLIKE
   * explorePromptId, this IS sent to the server (see api/submissions.ts): it is
   * what makes the contribution pay at that question's own kind-specific rate
   * instead of the generic Explore rate. Null for a free-form contribution or
   * one answering a device-built prompt.
   */
  placeQuestionId: string | null;
  /**
   * Provisional reward for an Explore contribution (Step 18), snapshotted from
   * the backend's reward config at capture time. Same contract as
   * LocalAnswer.rewardPoints: a display value for the offline case only, always
   * superseded by the server's authoritative total after sync. Null for
   * note/voice/location captures and for anything created before rewards
   * existed.
   */
  rewardPoints: number | null;
  /**
   * Location/date provenance — HOW this capture's coordinate and event time
   * were determined, not just WHAT they are. Mirrors the backend's
   * Submission columns exactly (app/db/models/submission.py) and is sent
   * verbatim on sync (see src/sync/syncService.ts) — the backend is the one
   * place these values are interpreted, so the mobile side never needs its
   * own copy of that logic.
   *
   * All are set at capture time by src/location/photoLocationResolver.ts (for
   * photo-bearing captures) or by the repository directly (for a plain
   * live GPS-tagged note/voice) — never edited afterwards.
   *
   * `latitude`/`longitude` reuse this row's existing... there is no existing
   * lat/lon column on LocalCapture (unlike LocalLocation), because until this
   * feature no capture type needed to carry its own coordinate — Explore's
   * location always came from the guide's live GuideLocation pings. These are
   * the first capture-level coordinates in this table.
   */
  latitude: number | null;
  longitude: number | null;
  locationSource: LocationSource;
  locationAccuracyMeters: number | null;
  /** ISO-8601 — when the COORDINATE was established (a GPS/EXIF timestamp),
   * distinct from `occurredAt` below (when the CONTENT is about) and from
   * `createdAt` (this local row's own bookkeeping time). */
  locationCapturedAt: string | null;
  /** Human-readable place name, from a geocoder selection or left null when
   * the coordinate came from GPS/EXIF (which already displays as a real
   * place via reverse lookup on the backend, not duplicated here). */
  locationLabel: string | null;
  /** Short factual note on why this location was assigned — mirrors the
   * backend's Submission.location_evidence exactly, e.g. "Matched to a GPS
   * sample 40 min after the photo's timestamp". Populated only for
   * historical-inference results the backend reports back; never fabricated
   * on-device. */
  locationEvidence: string | null;
  /** ISO-8601 — when the CONTENT is about, which may be long before
   * `createdAt` for an uploaded-later photo or memory. Null means "let the
   * backend default this to submitted-at", exactly like omitting it from the
   * API request (see app/services/submissions.py). */
  occurredAt: string | null;
  occurredAtPrecision: DatePrecision;
  dateSource: DateSource;
  syncStatus: SyncStatus;
  syncAttemptCount: number;
  lastSyncError: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * A GPS sample captured on this device (Step 6). Mirrors LocalCapture's outbox
 * shape exactly — same id/client-id/server-id/sync-status pattern — because it
 * goes through the same sync engine, just against a different backend endpoint
 * (POST /api/v1/guides/{guide_id}/locations instead of /api/v1/submissions).
 *
 * `id` is a local SQLite row id, not a backend location id. `clientLocationId` is
 * generated once at capture time and never regenerated. `serverLocationId` is
 * populated once the backend confirms receipt. `recordedAt` is when the device
 * captured the fix — distinct from `createdAt`/`updatedAt`, which are this local
 * row's own bookkeeping timestamps.
 */
export interface LocalLocation {
  id: number;
  localGuideId: number;
  clientLocationId: string;
  serverLocationId: string | null;
  latitude: number;
  longitude: number;
  accuracyMeters: number | null;
  recordedAt: string;
  syncStatus: SyncStatus;
  syncAttemptCount: number;
  lastSyncError: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * A guide's answer to an assigned question (Step 13), stored on this device
 * before it syncs. Same outbox shape as LocalCapture/LocalLocation — it goes
 * through the same sync engine, just against
 * `POST /api/v1/questions/{questionId}/answers`.
 *
 * `id` is a local SQLite row id, not a backend answer id. `serverQuestionId`
 * is the backend Question this answers (there is no local copy of questions —
 * see src/screens/QuestionsScreen.tsx — so this is the only link back to it).
 * `clientAnswerId` is generated once at answer time and never regenerated —
 * it is what makes the sync POST idempotent (see backend
 * QuestionAnswer.client_answer_id). `serverAnswerId` is populated once the
 * backend confirms the answer was persisted. There is at most one
 * LocalAnswer per `serverQuestionId` on this device (DB-enforced, see
 * src/db/database.ts) — this step has no re-answer/edit flow.
 */
export interface LocalAnswer {
  id: number;
  localGuideId: number;
  serverQuestionId: string;
  /**
   * Which question source this answers (Step 18), and therefore which backend
   * endpoint syncService must POST to:
   *
   * - 'dynamic' — a knowledge-gap question from the priority queue.
   *   `serverQuestionId` is a backend Question id; syncs to
   *   POST /api/v1/questions/{id}/answers.
   * - 'popular' — a researched question about the guide's current place.
   *   `serverQuestionId` is a backend PlaceQuestion id; syncs to
   *   POST /api/v1/place-questions/{id}/answers.
   *
   * The two id spaces are distinct server-side, so one column holds either
   * safely and the existing "one local answer per question" unique index keeps
   * its meaning for both.
   */
  questionKind: QuestionKind;
  clientAnswerId: string;
  serverAnswerId: string | null;
  answerText: string;
  answeredAt: string;
  /**
   * What the BACKEND said this answer was worth, snapshotted at answer time
   * from the question the guide was looking at. Never computed on the device.
   *
   * Its only job is to let an offline guide see "+25 points, pending sync"
   * backed by a real server-issued number instead of a guess. It is a
   * PROVISIONAL display value: once synced, `GET /guides/{id}/rewards` is the
   * authoritative total and supersedes any local arithmetic. Null for answers
   * created before rewards existed.
   */
  rewardPoints: number | null;
  syncStatus: SyncStatus;
  syncAttemptCount: number;
  lastSyncError: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * Device-level app preferences — NOT guide identity data, which is why this
 * is its own tiny key/value table rather than more columns on LocalGuide (see
 * src/db/database.ts's `local_settings` table). Reinstalling the app or
 * switching guides on the same device does not carry these over; they are a
 * property of this install, not of a person.
 */
export type AppSettingKey = 'auto_sync_enabled';
