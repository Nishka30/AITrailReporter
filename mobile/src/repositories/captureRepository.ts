import type { SQLiteDatabase } from 'expo-sqlite';

import { generateClientId } from '../db/uuid';
import type {
  CaptureType,
  DatePrecision,
  DateSource,
  LocalCapture,
  LocationSource,
  SyncStatus,
} from '../types/models';

interface LocalCaptureRow {
  id: number;
  local_guide_id: number;
  client_submission_id: string;
  server_submission_id: string | null;
  capture_type: string;
  text_content: string | null;
  local_audio_uri: string | null;
  client_audio_id: string | null;
  audio_duration_millis: number | null;
  audio_content_type: string | null;
  local_photo_uri: string | null;
  client_photo_id: string | null;
  photo_content_type: string | null;
  explore_prompt_id: string | null;
  explore_prompt_title: string | null;
  place_question_id: string | null;
  reward_points: number | null;
  latitude: number | null;
  longitude: number | null;
  location_source: string;
  location_accuracy_meters: number | null;
  location_captured_at: string | null;
  location_label: string | null;
  location_evidence: string | null;
  occurred_at: string | null;
  occurred_at_precision: string;
  date_source: string;
  sync_status: string;
  sync_attempt_count: number;
  last_sync_error: string | null;
  created_at: string;
  updated_at: string;
}

/** Location/date provenance fields shared by createExploreCapture and
 * createMemoryCapture — see LocalCapture in types/models.ts for what each
 * one means. All optional: a caller supplies whatever
 * src/location/photoLocationResolver.ts (or a plain live GPS read) actually
 * determined, never a guess to fill a gap. */
export interface CaptureProvenanceInput {
  latitude?: number | null;
  longitude?: number | null;
  locationSource?: LocationSource;
  locationAccuracyMeters?: number | null;
  locationCapturedAt?: string | null;
  locationLabel?: string | null;
  locationEvidence?: string | null;
  occurredAt?: string | null;
  occurredAtPrecision?: DatePrecision;
  dateSource?: DateSource;
}

// Statuses eligible for a sync attempt: never-yet-sent, previously-failed
// (retryable), and 'uploading'. 'uploading' is included deliberately: the
// in-process sync lock (see src/sync/syncService.ts) only prevents two concurrent
// syncAll() calls within the SAME app session — it does not survive an app
// restart. If the app is killed mid-request, a capture can be left stuck at
// 'uploading' with no in-flight request actually still running. Since this list is
// read once at the START of a fresh syncAll() run, any row already 'uploading' at
// that point can only be such a leftover, never a request this run itself is
// making — so it's safe, and necessary, to retry it.
const SYNCABLE_STATUSES: SyncStatus[] = ['pending', 'failed', 'uploading'];

function mapRow(row: LocalCaptureRow): LocalCapture {
  return {
    id: row.id,
    localGuideId: row.local_guide_id,
    clientSubmissionId: row.client_submission_id,
    serverSubmissionId: row.server_submission_id,
    captureType: row.capture_type as CaptureType,
    textContent: row.text_content,
    localAudioUri: row.local_audio_uri,
    clientAudioId: row.client_audio_id,
    audioDurationMillis: row.audio_duration_millis,
    audioContentType: row.audio_content_type,
    localPhotoUri: row.local_photo_uri,
    clientPhotoId: row.client_photo_id,
    photoContentType: row.photo_content_type,
    explorePromptId: row.explore_prompt_id,
    explorePromptTitle: row.explore_prompt_title,
    placeQuestionId: row.place_question_id,
    rewardPoints: row.reward_points,
    latitude: row.latitude,
    longitude: row.longitude,
    locationSource: row.location_source as LocationSource,
    locationAccuracyMeters: row.location_accuracy_meters,
    locationCapturedAt: row.location_captured_at,
    locationLabel: row.location_label,
    locationEvidence: row.location_evidence,
    occurredAt: row.occurred_at,
    occurredAtPrecision: row.occurred_at_precision as DatePrecision,
    dateSource: row.date_source as DateSource,
    syncStatus: row.sync_status as SyncStatus,
    syncAttemptCount: row.sync_attempt_count,
    lastSyncError: row.last_sync_error,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

/**
 * Stores a capture locally with sync_status = 'pending', generating its stable
 * client_submission_id once. Purely local — does not call the backend. "pending"
 * means "captured safely on this device and not yet sent to the server."
 */
export async function createCapture(
  db: SQLiteDatabase,
  localGuideId: number,
  captureType: CaptureType,
  textContent: string | null
): Promise<LocalCapture> {
  const now = new Date().toISOString();
  const clientSubmissionId = generateClientId();
  const result = await db.runAsync(
    `INSERT INTO local_capture
       (local_guide_id, client_submission_id, capture_type, text_content, sync_status, created_at, updated_at)
     VALUES (?, ?, ?, ?, 'pending', ?, ?)`,
    localGuideId,
    clientSubmissionId,
    captureType,
    textContent,
    now,
    now
  );

  const row = await db.getFirstAsync<LocalCaptureRow>(
    'SELECT * FROM local_capture WHERE id = ?',
    result.lastInsertRowId
  );
  if (!row) {
    throw new Error('Failed to read back the newly created local capture.');
  }
  return mapRow(row);
}

/**
 * Stores a voice recording locally with sync_status = 'pending'. Generates TWO
 * stable ids, once, here: clientSubmissionId (makes creating the server
 * Submission idempotent, same as a note) and clientAudioId (a separate id that
 * makes the audio upload step — a distinct backend request during sync —
 * independently idempotent/retryable; see src/sync/syncService.ts). Purely
 * local — does not call the backend and does not touch the audio file itself,
 * which must already exist on disk at `localAudioUri` before this is called.
 */
export async function createVoiceCapture(
  db: SQLiteDatabase,
  localGuideId: number,
  localAudioUri: string,
  audioDurationMillis: number | null,
  audioContentType: string
): Promise<LocalCapture> {
  const now = new Date().toISOString();
  const clientSubmissionId = generateClientId();
  const clientAudioId = generateClientId();
  const result = await db.runAsync(
    `INSERT INTO local_capture
       (local_guide_id, client_submission_id, capture_type, text_content,
        local_audio_uri, client_audio_id, audio_duration_millis, audio_content_type,
        sync_status, created_at, updated_at)
     VALUES (?, ?, 'voice', NULL, ?, ?, ?, ?, 'pending', ?, ?)`,
    localGuideId,
    clientSubmissionId,
    localAudioUri,
    clientAudioId,
    audioDurationMillis,
    audioContentType,
    now,
    now
  );

  const row = await db.getFirstAsync<LocalCaptureRow>(
    'SELECT * FROM local_capture WHERE id = ?',
    result.lastInsertRowId
  );
  if (!row) {
    throw new Error('Failed to read back the newly created local voice capture.');
  }
  return mapRow(row);
}

/**
 * Stores an Explore discovery contribution locally with sync_status =
 * 'pending' (Step 16, extended in Step 17). Purely local — does not call the
 * backend and does not touch the media files themselves, which must already
 * exist on disk before this is called (the picker copies photos into app
 * storage — see src/photo/photoPickerService.ts — and expo-audio records
 * straight into the document directory).
 *
 * A contribution must carry TEXT or a VOICE NOTE (the caller enforces this; see
 * ExploreContributeScreen). Both become observations through the existing
 * extraction pipeline: text directly, voice via the existing transcription
 * step. A photo alone is never enough, because nothing in this system reads
 * images — the photo is durable evidence attached alongside, not content.
 *
 * Generates clientSubmissionId always, plus clientPhotoId ONLY when a photo is
 * attached and clientAudioId ONLY when a recording is attached. Those nulls are
 * load-bearing: they are exactly what tells the sync engine which of the
 * optional upload stages to perform for this row.
 *
 * The audio columns reused here (local_audio_uri, client_audio_id,
 * audio_duration_millis, audio_content_type) are the SAME ones voice notes have
 * used since v4 — no Explore-specific audio columns exist, on purpose.
 */
interface ExploreLikeOptions extends CaptureProvenanceInput {
  localPhotoUri?: string | null;
  photoContentType?: string | null;
  localAudioUri?: string | null;
  audioDurationMillis?: number | null;
  audioContentType?: string | null;
  promptId?: string | null;
  promptTitle?: string | null;
  /** Set when this contribution answers a backend-researched place question.
   * Unlike promptId/promptTitle (which are local-only provenance for
   * device-built Explore prompts), this IS sent to the server — it is what
   * makes the contribution pay at that question's own rate. Never set for a
   * 'memory' capture — a memory is never tied to a specific place question. */
  placeQuestionId?: string | null;
  /** What the BACKEND said this contribution was worth at the moment it was
   * composed. Snapshotted so an offline guide sees a real server-issued
   * number rather than a device guess; the server remains authoritative. */
  rewardPoints?: number | null;
}

/**
 * Shared insert for 'explore' and 'memory' captures — identical shape on both
 * sides (same optional text/photo/voice, same idempotency-id generation),
 * differing only in `captureType` and in which public wrapper enforces which
 * "must have SOMETHING" rule (see createExploreCapture/createMemoryCapture
 * below). Kept private: callers use the two named wrappers so that rule is
 * never accidentally skipped.
 */
async function insertExploreLikeCapture(
  db: SQLiteDatabase,
  localGuideId: number,
  captureType: 'explore' | 'memory',
  textContent: string | null,
  options: ExploreLikeOptions
): Promise<LocalCapture> {
  const trimmedText = textContent?.trim() ? textContent.trim() : null;
  const localPhotoUri = options.localPhotoUri ?? null;
  const localAudioUri = options.localAudioUri ?? null;

  const now = new Date().toISOString();
  const clientSubmissionId = generateClientId();
  const clientPhotoId = localPhotoUri ? generateClientId() : null;
  const clientAudioId = localAudioUri ? generateClientId() : null;

  const result = await db.runAsync(
    `INSERT INTO local_capture
       (local_guide_id, client_submission_id, capture_type, text_content,
        local_photo_uri, client_photo_id, photo_content_type,
        local_audio_uri, client_audio_id, audio_duration_millis, audio_content_type,
        explore_prompt_id, explore_prompt_title,
        place_question_id, reward_points,
        latitude, longitude, location_source, location_accuracy_meters,
        location_captured_at, location_label, location_evidence,
        occurred_at, occurred_at_precision, date_source,
        sync_status, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
             ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
             'pending', ?, ?)`,
    localGuideId,
    clientSubmissionId,
    captureType,
    trimmedText,
    localPhotoUri,
    clientPhotoId,
    localPhotoUri ? (options.photoContentType ?? null) : null,
    localAudioUri,
    clientAudioId,
    localAudioUri ? (options.audioDurationMillis ?? null) : null,
    localAudioUri ? (options.audioContentType ?? null) : null,
    options.promptId ?? null,
    options.promptTitle ?? null,
    options.placeQuestionId ?? null,
    options.rewardPoints ?? null,
    options.latitude ?? null,
    options.longitude ?? null,
    options.locationSource ?? 'unknown',
    options.locationAccuracyMeters ?? null,
    options.locationCapturedAt ?? null,
    options.locationLabel ?? null,
    options.locationEvidence ?? null,
    options.occurredAt ?? null,
    options.occurredAtPrecision ?? 'unknown',
    options.dateSource ?? 'unknown',
    now,
    now
  );

  const row = await db.getFirstAsync<LocalCaptureRow>(
    'SELECT * FROM local_capture WHERE id = ?',
    result.lastInsertRowId
  );
  if (!row) {
    throw new Error(`Failed to read back the newly created ${captureType} contribution.`);
  }
  return mapRow(row);
}

export async function createExploreCapture(
  db: SQLiteDatabase,
  localGuideId: number,
  textContent: string | null,
  options: ExploreLikeOptions = {}
): Promise<LocalCapture> {
  const trimmedText = textContent?.trim();
  if (!trimmedText && !options.localAudioUri) {
    // Guarded here as well as in the UI: a contribution with neither text nor
    // audio has nothing that could ever become knowledge, and silently storing
    // one would create a row that syncs successfully and then dead-ends.
    throw new Error('An Explore contribution needs either a description or a voice note.');
  }
  return insertExploreLikeCapture(db, localGuideId, 'explore', textContent, options);
}

/**
 * Stores a "memory" contribution locally — the same shape as an Explore
 * contribution, but not tied to a live moment or a verified place (an old
 * photo, a recalled story). See LocalCapture's location.../occurredAt... fields
 * and src/screens/MemoryContributeScreen.tsx for how provenance is actually
 * determined before this is called.
 *
 * Deliberately a LOOSER "must have something" rule than Explore: a memory
 * that is JUST an old photo with no caption is still a meaningful
 * contribution — the photo is durable evidence even if nothing here becomes
 * an Observation (extraction needs text; see
 * backend/app/services/submissions.py's photo-attach docstring). Explore
 * keeps its stricter text-or-voice rule unchanged.
 */
export async function createMemoryCapture(
  db: SQLiteDatabase,
  localGuideId: number,
  textContent: string | null,
  options: ExploreLikeOptions = {}
): Promise<LocalCapture> {
  const trimmedText = textContent?.trim();
  if (!trimmedText && !options.localAudioUri && !options.localPhotoUri) {
    throw new Error('A memory needs a photo, a voice note, or a description.');
  }
  return insertExploreLikeCapture(db, localGuideId, 'memory', textContent, options);
}

export async function listCaptures(
  db: SQLiteDatabase,
  localGuideId: number
): Promise<LocalCapture[]> {
  const rows = await db.getAllAsync<LocalCaptureRow>(
    'SELECT * FROM local_capture WHERE local_guide_id = ? ORDER BY created_at DESC',
    localGuideId
  );
  return rows.map(mapRow);
}

export async function getCaptureById(
  db: SQLiteDatabase,
  id: number
): Promise<LocalCapture | null> {
  const row = await db.getFirstAsync<LocalCaptureRow>(
    'SELECT * FROM local_capture WHERE id = ?',
    id
  );
  return row ? mapRow(row) : null;
}

export async function countPendingCaptures(
  db: SQLiteDatabase,
  localGuideId: number
): Promise<number> {
  const row = await db.getFirstAsync<{ count: number }>(
    `SELECT COUNT(*) as count FROM local_capture
     WHERE local_guide_id = ? AND sync_status = 'pending'`,
    localGuideId
  );
  return row?.count ?? 0;
}

/**
 * Count of captures in any of the given statuses, for this guide. `captureTypes`
 * optionally narrows to specific capture types (e.g. ['voice']) — omitted means
 * "any type", preserving the original all-captures behavior for existing callers.
 */
export async function countCapturesByStatus(
  db: SQLiteDatabase,
  localGuideId: number,
  statuses: SyncStatus[],
  captureTypes?: CaptureType[]
): Promise<number> {
  if (statuses.length === 0) return 0;
  const statusPlaceholders = statuses.map(() => '?').join(', ');
  let query = `SELECT COUNT(*) as count FROM local_capture
     WHERE local_guide_id = ? AND sync_status IN (${statusPlaceholders})`;
  const params: (string | number)[] = [localGuideId, ...statuses];
  if (captureTypes && captureTypes.length > 0) {
    const typePlaceholders = captureTypes.map(() => '?').join(', ');
    query += ` AND capture_type IN (${typePlaceholders})`;
    params.push(...captureTypes);
  }
  const row = await db.getFirstAsync<{ count: number }>(query, ...params);
  return row?.count ?? 0;
}

/**
 * Captures eligible for a sync attempt, oldest created_at first — see
 * SYNCABLE_STATUSES above for exactly which statuses that includes and why. Never
 * includes 'uploaded' (already confirmed by the server) or any future
 * 'processing'/'synced' status — those are not re-sent.
 */
export async function listSyncableCaptures(
  db: SQLiteDatabase,
  localGuideId: number
): Promise<LocalCapture[]> {
  const placeholders = SYNCABLE_STATUSES.map(() => '?').join(', ');
  const rows = await db.getAllAsync<LocalCaptureRow>(
    `SELECT * FROM local_capture
     WHERE local_guide_id = ? AND sync_status IN (${placeholders})
     ORDER BY created_at ASC`,
    localGuideId,
    ...SYNCABLE_STATUSES
  );
  return rows.map(mapRow);
}

/** Marks a capture as actively being sent, and counts this as a sync attempt. */
export async function markCaptureUploading(db: SQLiteDatabase, id: number): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_capture
     SET sync_status = 'uploading', sync_attempt_count = sync_attempt_count + 1, updated_at = ?
     WHERE id = ?`,
    now,
    id
  );
}

/** Marks a capture as confirmed received by the backend. This is NOT "processed". */
export async function markCaptureUploaded(
  db: SQLiteDatabase,
  id: number,
  serverSubmissionId: string
): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_capture
     SET sync_status = 'uploaded', server_submission_id = ?, last_sync_error = NULL, updated_at = ?
     WHERE id = ?`,
    serverSubmissionId,
    now,
    id
  );
}

/** Marks a capture's last sync attempt as failed. It remains stored and retryable. */
export async function markCaptureFailed(
  db: SQLiteDatabase,
  id: number,
  errorMessage: string
): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_capture
     SET sync_status = 'failed', last_sync_error = ?, updated_at = ?
     WHERE id = ?`,
    errorMessage,
    now,
    id
  );
}
