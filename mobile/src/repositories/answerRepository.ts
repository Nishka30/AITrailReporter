import type { SQLiteDatabase } from 'expo-sqlite';

import { generateClientId } from '../db/uuid';
import { isValidCoordinatePair } from '../location/coordinateValidation';
import type { LocalAnswer, QuestionKind, SyncStatus } from '../types/models';

interface LocalAnswerRow {
  id: number;
  local_guide_id: number;
  server_question_id: string;
  question_kind: string;
  client_answer_id: string;
  server_answer_id: string | null;
  server_submission_id: string | null;
  answer_text: string;
  answered_at: string;
  reward_points: number | null;
  local_audio_uri: string | null;
  client_audio_id: string | null;
  audio_duration_millis: number | null;
  audio_content_type: string | null;
  local_photo_uri: string | null;
  client_photo_id: string | null;
  photo_content_type: string | null;
  sync_status: string;
  sync_attempt_count: number;
  last_sync_error: string | null;
  latitude: number | null;
  longitude: number | null;
  location_accuracy_meters: number | null;
  location_captured_at: string | null;
  location_label: string | null;
  external_place_id: string | null;
  review_status: string | null;
  rejection_reason: string | null;
  rejection_note: string | null;
  reward_points_awarded: number | null;
  created_at: string;
  updated_at: string;
}

// Same rationale as SYNCABLE_STATUSES in captureRepository.ts/locationRepository.ts:
// 'uploading' is included because the in-process sync lock doesn't survive an
// app restart, so an answer stuck 'uploading' from a killed session must
// still be retried, not orphaned.
const SYNCABLE_STATUSES: SyncStatus[] = ['pending', 'failed', 'uploading'];

/** Optional media captured alongside an answer's text. */
export interface AnswerMediaInput {
  localAudioUri?: string | null;
  audioDurationMillis?: number | null;
  audioContentType?: string | null;
  localPhotoUri?: string | null;
  photoContentType?: string | null;
}

/**
 * Where the guide was when they answered, if they captured it (see
 * components/LocationCaptureField.tsx). Entirely optional: omitting it leaves
 * every column null and the server keeps deriving the coordinate the way it
 * always has.
 */
export interface AnswerLocationInput {
  latitude?: number | null;
  longitude?: number | null;
  locationAccuracyMeters?: number | null;
  locationCapturedAt?: string | null;
  locationLabel?: string | null;
  externalPlaceId?: string | null;
}

function mapRow(row: LocalAnswerRow): LocalAnswer {
  return {
    id: row.id,
    localGuideId: row.local_guide_id,
    serverQuestionId: row.server_question_id,
    questionKind: (row.question_kind as QuestionKind) ?? 'dynamic',
    clientAnswerId: row.client_answer_id,
    serverAnswerId: row.server_answer_id,
    serverSubmissionId: row.server_submission_id,
    answerText: row.answer_text,
    answeredAt: row.answered_at,
    rewardPoints: row.reward_points,
    localAudioUri: row.local_audio_uri,
    clientAudioId: row.client_audio_id,
    audioDurationMillis: row.audio_duration_millis,
    audioContentType: row.audio_content_type,
    localPhotoUri: row.local_photo_uri,
    clientPhotoId: row.client_photo_id,
    photoContentType: row.photo_content_type,
    syncStatus: row.sync_status as SyncStatus,
    syncAttemptCount: row.sync_attempt_count,
    lastSyncError: row.last_sync_error,
    latitude: row.latitude,
    longitude: row.longitude,
    locationAccuracyMeters: row.location_accuracy_meters,
    locationCapturedAt: row.location_captured_at,
    locationLabel: row.location_label,
    externalPlaceId: row.external_place_id,
    reviewStatus: row.review_status as LocalAnswer['reviewStatus'],
    rejectionReason: row.rejection_reason,
    rejectionNote: row.rejection_note,
    rewardPointsAwarded: row.reward_points_awarded,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

/**
 * Stores a guide's answer to a question locally with sync_status = 'pending',
 * generating its stable client_answer_id once. Purely local — does not call
 * the backend, so this succeeds with no network at all. `answeredAt` is the
 * device-local time the guide actually answered (not when it later syncs).
 *
 * Fails (via the DB's UNIQUE constraint on server_question_id) if this
 * question already has a local answer — the caller (AnswerQuestionScreen)
 * should check with `getAnswerByQuestionId` first and show the existing
 * answer read-only instead of re-prompting.
 */
export async function createAnswer(
  db: SQLiteDatabase,
  localGuideId: number,
  serverQuestionId: string,
  answerText: string,
  answeredAt: string,
  /** Which question source this answers — determines the sync endpoint.
   * Defaults to 'dynamic' so every existing caller keeps its exact behaviour. */
  questionKind: QuestionKind = 'dynamic',
  /** What the backend said this question was worth, snapshotted so an offline
   * guide sees a real server-issued number rather than a guess. Null when the
   * reward wasn't known (e.g. the question list was served from cache before
   * rewards existed). */
  rewardPoints: number | null = null,
  /** Optional photo/voice note captured alongside the text. Each gets its own
   * client id here so the two uploads stay independently idempotent, exactly
   * as captures do (see captureRepository). */
  media: AnswerMediaInput = {},
  /** The guide's own position at answer time, when they captured one. */
  location: AnswerLocationInput = {}
): Promise<LocalAnswer> {
  // Write-boundary guard against (0, 0) -- same rule and same reasoning as
  // captureRepository.ts's sanitizeProvenanceCoordinates: applied here, at
  // the actual INSERT, so it protects this table regardless of which
  // upstream capture path (LocationCaptureField's GPS capture is currently
  // the only source for an answer's location) fed it. An invalid pair is
  // dropped entirely rather than persisted -- see
  // coordinateValidation.ts's module docstring.
  const safeLocation: AnswerLocationInput =
    location.latitude != null || location.longitude != null
      ? isValidCoordinatePair(location.latitude, location.longitude)
        ? location
        : { ...location, latitude: null, longitude: null }
      : location;
  const now = new Date().toISOString();
  const clientAnswerId = generateClientId();
  const clientAudioId = media.localAudioUri ? generateClientId() : null;
  const clientPhotoId = media.localPhotoUri ? generateClientId() : null;
  const result = await db.runAsync(
    `INSERT INTO local_answer
       (local_guide_id, server_question_id, question_kind, client_answer_id, answer_text, answered_at, reward_points,
        local_audio_uri, client_audio_id, audio_duration_millis, audio_content_type,
        local_photo_uri, client_photo_id, photo_content_type,
        latitude, longitude, location_accuracy_meters, location_captured_at, location_label, external_place_id,
        sync_status, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)`,
    localGuideId,
    serverQuestionId,
    questionKind,
    clientAnswerId,
    answerText,
    answeredAt,
    rewardPoints,
    media.localAudioUri ?? null,
    clientAudioId,
    media.audioDurationMillis ?? null,
    media.audioContentType ?? null,
    media.localPhotoUri ?? null,
    clientPhotoId,
    media.photoContentType ?? null,
    safeLocation.latitude ?? null,
    safeLocation.longitude ?? null,
    safeLocation.locationAccuracyMeters ?? null,
    safeLocation.locationCapturedAt ?? null,
    safeLocation.locationLabel ?? null,
    safeLocation.externalPlaceId ?? null,
    now,
    now
  );

  const row = await db.getFirstAsync<LocalAnswerRow>(
    'SELECT * FROM local_answer WHERE id = ?',
    result.lastInsertRowId
  );
  if (!row) {
    throw new Error('Failed to read back the newly created local answer.');
  }
  return mapRow(row);
}

/** The local answer for this server question, if the guide has already
 * answered it on this device (regardless of sync status) — null otherwise. */
export async function getAnswerByQuestionId(
  db: SQLiteDatabase,
  serverQuestionId: string
): Promise<LocalAnswer | null> {
  const row = await db.getFirstAsync<LocalAnswerRow>(
    'SELECT * FROM local_answer WHERE server_question_id = ?',
    serverQuestionId
  );
  return row ? mapRow(row) : null;
}

/**
 * Records the admin-approval decision reported for this answer (Step 19),
 * matched by `clientAnswerId` -- the server stores this as the underlying
 * Submission's client_submission_id, and echoes it back on every read (see
 * sync/submissionReviewSync.ts, the only caller).
 */
export async function updateAnswerReviewStatus(
  db: SQLiteDatabase,
  clientAnswerId: string,
  status: LocalAnswer['reviewStatus'],
  rejectionReason: string | null,
  rejectionNote: string | null,
  rewardPointsAwarded: number | null
): Promise<void> {
  await db.runAsync(
    `UPDATE local_answer
     SET review_status = ?, rejection_reason = ?, rejection_note = ?, reward_points_awarded = ?
     WHERE client_answer_id = ?`,
    status,
    rejectionReason,
    rejectionNote,
    rewardPointsAwarded,
    clientAnswerId
  );
}

/** Count of local answers in any of the given statuses, for this guide —
 * mirrors countCapturesByStatus/countLocationsByStatus (Step 15: used for
 * the Activity tab badge). */
export async function countAnswersByStatus(
  db: SQLiteDatabase,
  localGuideId: number,
  statuses: SyncStatus[]
): Promise<number> {
  if (statuses.length === 0) return 0;
  const placeholders = statuses.map(() => '?').join(', ');
  const row = await db.getFirstAsync<{ count: number }>(
    `SELECT COUNT(*) as count FROM local_answer
     WHERE local_guide_id = ? AND sync_status IN (${placeholders})`,
    localGuideId,
    ...statuses
  );
  return row?.count ?? 0;
}

/** Every local answer for this guide, most recently answered first — used by
 * QuestionsScreen to merge local answer state onto the server's question list. */
export async function listAnswersForGuide(
  db: SQLiteDatabase,
  localGuideId: number
): Promise<LocalAnswer[]> {
  const rows = await db.getAllAsync<LocalAnswerRow>(
    'SELECT * FROM local_answer WHERE local_guide_id = ? ORDER BY answered_at DESC',
    localGuideId
  );
  return rows.map(mapRow);
}

/** Answers eligible for a sync attempt (see SYNCABLE_STATUSES above), oldest
 * answered_at first. Never includes 'uploaded'. */
export async function listSyncableAnswers(
  db: SQLiteDatabase,
  localGuideId: number
): Promise<LocalAnswer[]> {
  const placeholders = SYNCABLE_STATUSES.map(() => '?').join(', ');
  const rows = await db.getAllAsync<LocalAnswerRow>(
    `SELECT * FROM local_answer
     WHERE local_guide_id = ? AND sync_status IN (${placeholders})
     ORDER BY answered_at ASC`,
    localGuideId,
    ...SYNCABLE_STATUSES
  );
  return rows.map(mapRow);
}

/**
 * Points the guide has provisionally earned on this device for answers still
 * waiting to reach the SERVER (Step 18) -- i.e. not yet synced at all. This
 * is about TRANSPORT, not about admin approval (Step 19): an answer that has
 * synced still is not in the authoritative total until an admin approves it
 * (see submission_reviews), but it is also correctly excluded from this
 * "waiting to sync" count, since sync is exactly what it's no longer waiting
 * on.
 *
 * Deliberately excludes 'uploaded' rows for that reason: once the backend has
 * the answer, this "waiting to sync" number no longer applies to it -- its
 * fate is now "pending admin approval" / "approved" / "rejected", which
 * PendingItemsScreen shows per-item from `review_status`, not summed here.
 * This number is only ever shown as a separate "waiting to sync" line, never
 * added into the confirmed balance by the app.
 */
export async function sumPendingRewardPoints(
  db: SQLiteDatabase,
  localGuideId: number
): Promise<number> {
  const row = await db.getFirstAsync<{ total: number | null }>(
    `SELECT SUM(reward_points) as total FROM local_answer
     WHERE local_guide_id = ? AND reward_points IS NOT NULL
       AND sync_status NOT IN ('uploaded', 'synced')`,
    localGuideId
  );
  return row?.total ?? 0;
}

/** Marks an answer as actively being sent, and counts this as a sync attempt. */
export async function markAnswerUploading(db: SQLiteDatabase, id: number): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_answer
     SET sync_status = 'uploading', sync_attempt_count = sync_attempt_count + 1, updated_at = ?
     WHERE id = ?`,
    now,
    id
  );
}

/**
 * Marks an answer as confirmed received and persisted by the backend.
 *
 * Records the submission id separately from the answer id: they are the same
 * value for a 'popular' answer but genuinely different for a 'dynamic' one,
 * and the Activity screen needs the SUBMISSION to offer transcription and
 * extraction (see LocalAnswer.serverSubmissionId).
 */
export async function markAnswerUploaded(
  db: SQLiteDatabase,
  id: number,
  serverAnswerId: string,
  serverSubmissionId: string
): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_answer
     SET sync_status = 'uploaded', server_answer_id = ?, server_submission_id = ?,
         last_sync_error = NULL, updated_at = ?
     WHERE id = ?`,
    serverAnswerId,
    serverSubmissionId,
    now,
    id
  );
}

/** Marks an answer's last sync attempt as failed. It remains stored and retryable. */
export async function markAnswerFailed(
  db: SQLiteDatabase,
  id: number,
  errorMessage: string
): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_answer
     SET sync_status = 'failed', last_sync_error = ?, updated_at = ?
     WHERE id = ?`,
    errorMessage,
    now,
    id
  );
}
