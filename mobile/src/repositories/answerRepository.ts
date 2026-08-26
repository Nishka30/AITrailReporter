import type { SQLiteDatabase } from 'expo-sqlite';

import { generateClientId } from '../db/uuid';
import type { LocalAnswer, SyncStatus } from '../types/models';

interface LocalAnswerRow {
  id: number;
  local_guide_id: number;
  server_question_id: string;
  client_answer_id: string;
  server_answer_id: string | null;
  answer_text: string;
  answered_at: string;
  sync_status: string;
  sync_attempt_count: number;
  last_sync_error: string | null;
  created_at: string;
  updated_at: string;
}

// Same rationale as SYNCABLE_STATUSES in captureRepository.ts/locationRepository.ts:
// 'uploading' is included because the in-process sync lock doesn't survive an
// app restart, so an answer stuck 'uploading' from a killed session must
// still be retried, not orphaned.
const SYNCABLE_STATUSES: SyncStatus[] = ['pending', 'failed', 'uploading'];

function mapRow(row: LocalAnswerRow): LocalAnswer {
  return {
    id: row.id,
    localGuideId: row.local_guide_id,
    serverQuestionId: row.server_question_id,
    clientAnswerId: row.client_answer_id,
    serverAnswerId: row.server_answer_id,
    answerText: row.answer_text,
    answeredAt: row.answered_at,
    syncStatus: row.sync_status as SyncStatus,
    syncAttemptCount: row.sync_attempt_count,
    lastSyncError: row.last_sync_error,
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
  answeredAt: string
): Promise<LocalAnswer> {
  const now = new Date().toISOString();
  const clientAnswerId = generateClientId();
  const result = await db.runAsync(
    `INSERT INTO local_answer
       (local_guide_id, server_question_id, client_answer_id, answer_text, answered_at, sync_status, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)`,
    localGuideId,
    serverQuestionId,
    clientAnswerId,
    answerText,
    answeredAt,
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

/** Marks an answer as confirmed received and persisted by the backend. */
export async function markAnswerUploaded(
  db: SQLiteDatabase,
  id: number,
  serverAnswerId: string
): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_answer
     SET sync_status = 'uploaded', server_answer_id = ?, last_sync_error = NULL, updated_at = ?
     WHERE id = ?`,
    serverAnswerId,
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
