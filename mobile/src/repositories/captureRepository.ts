import type { SQLiteDatabase } from 'expo-sqlite';

import { generateClientId } from '../db/uuid';
import type { CaptureType, LocalCapture, SyncStatus } from '../types/models';

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
  sync_status: string;
  sync_attempt_count: number;
  last_sync_error: string | null;
  created_at: string;
  updated_at: string;
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
