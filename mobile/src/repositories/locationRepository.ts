import type { SQLiteDatabase } from 'expo-sqlite';

import { generateClientId } from '../db/uuid';
import type { LocalLocation, SyncStatus } from '../types/models';

interface LocalLocationRow {
  id: number;
  local_guide_id: number;
  client_location_id: string;
  server_location_id: string | null;
  latitude: number;
  longitude: number;
  accuracy_meters: number | null;
  recorded_at: string;
  sync_status: string;
  sync_attempt_count: number;
  last_sync_error: string | null;
  created_at: string;
  updated_at: string;
}

// Same rationale as SYNCABLE_STATUSES in captureRepository.ts: 'uploading' is
// included because the in-process sync lock doesn't survive an app restart, so a
// sample stuck 'uploading' from a killed session must still be retried, not
// orphaned. See that file's comment for the full explanation.
const SYNCABLE_STATUSES: SyncStatus[] = ['pending', 'failed', 'uploading'];

function mapRow(row: LocalLocationRow): LocalLocation {
  return {
    id: row.id,
    localGuideId: row.local_guide_id,
    clientLocationId: row.client_location_id,
    serverLocationId: row.server_location_id,
    latitude: row.latitude,
    longitude: row.longitude,
    accuracyMeters: row.accuracy_meters,
    recordedAt: row.recorded_at,
    syncStatus: row.sync_status as SyncStatus,
    syncAttemptCount: row.sync_attempt_count,
    lastSyncError: row.last_sync_error,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

/**
 * Stores a GPS sample locally with sync_status = 'pending', generating its stable
 * client_location_id once. Purely local — does not call the backend. The sample is
 * durable on the device before anything network-related is ever attempted.
 */
export async function createLocation(
  db: SQLiteDatabase,
  localGuideId: number,
  latitude: number,
  longitude: number,
  accuracyMeters: number | null,
  recordedAt: string
): Promise<LocalLocation> {
  const now = new Date().toISOString();
  const clientLocationId = generateClientId();
  const result = await db.runAsync(
    `INSERT INTO local_location
       (local_guide_id, client_location_id, latitude, longitude, accuracy_meters, recorded_at, sync_status, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)`,
    localGuideId,
    clientLocationId,
    latitude,
    longitude,
    accuracyMeters,
    recordedAt,
    now,
    now
  );

  const row = await db.getFirstAsync<LocalLocationRow>(
    'SELECT * FROM local_location WHERE id = ?',
    result.lastInsertRowId
  );
  if (!row) {
    throw new Error('Failed to read back the newly created local location.');
  }
  return mapRow(row);
}

export async function getLocationById(
  db: SQLiteDatabase,
  id: number
): Promise<LocalLocation | null> {
  const row = await db.getFirstAsync<LocalLocationRow>(
    'SELECT * FROM local_location WHERE id = ?',
    id
  );
  return row ? mapRow(row) : null;
}

/** Most recently RECORDED sample (by recorded_at, not insertion order). */
export async function getLatestLocation(
  db: SQLiteDatabase,
  localGuideId: number
): Promise<LocalLocation | null> {
  const row = await db.getFirstAsync<LocalLocationRow>(
    `SELECT * FROM local_location
     WHERE local_guide_id = ?
     ORDER BY recorded_at DESC
     LIMIT 1`,
    localGuideId
  );
  return row ? mapRow(row) : null;
}

export async function listLocations(
  db: SQLiteDatabase,
  localGuideId: number
): Promise<LocalLocation[]> {
  const rows = await db.getAllAsync<LocalLocationRow>(
    'SELECT * FROM local_location WHERE local_guide_id = ? ORDER BY recorded_at DESC',
    localGuideId
  );
  return rows.map(mapRow);
}

/** Count of locations in any of the given statuses, for this guide. */
export async function countLocationsByStatus(
  db: SQLiteDatabase,
  localGuideId: number,
  statuses: SyncStatus[]
): Promise<number> {
  if (statuses.length === 0) return 0;
  const placeholders = statuses.map(() => '?').join(', ');
  const row = await db.getFirstAsync<{ count: number }>(
    `SELECT COUNT(*) as count FROM local_location
     WHERE local_guide_id = ? AND sync_status IN (${placeholders})`,
    localGuideId,
    ...statuses
  );
  return row?.count ?? 0;
}

/**
 * Locations eligible for a sync attempt (see SYNCABLE_STATUSES above), oldest
 * recorded_at first. Never includes 'uploaded'.
 */
export async function listSyncableLocations(
  db: SQLiteDatabase,
  localGuideId: number
): Promise<LocalLocation[]> {
  const placeholders = SYNCABLE_STATUSES.map(() => '?').join(', ');
  const rows = await db.getAllAsync<LocalLocationRow>(
    `SELECT * FROM local_location
     WHERE local_guide_id = ? AND sync_status IN (${placeholders})
     ORDER BY recorded_at ASC`,
    localGuideId,
    ...SYNCABLE_STATUSES
  );
  return rows.map(mapRow);
}

/** Marks a location as actively being sent, and counts this as a sync attempt. */
export async function markLocationUploading(db: SQLiteDatabase, id: number): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_location
     SET sync_status = 'uploading', sync_attempt_count = sync_attempt_count + 1, updated_at = ?
     WHERE id = ?`,
    now,
    id
  );
}

/** Marks a location as confirmed received by the backend. This is NOT "processed". */
export async function markLocationUploaded(
  db: SQLiteDatabase,
  id: number,
  serverLocationId: string
): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_location
     SET sync_status = 'uploaded', server_location_id = ?, last_sync_error = NULL, updated_at = ?
     WHERE id = ?`,
    serverLocationId,
    now,
    id
  );
}

/** Marks a location's last sync attempt as failed. It remains stored and retryable. */
export async function markLocationFailed(
  db: SQLiteDatabase,
  id: number,
  errorMessage: string
): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_location
     SET sync_status = 'failed', last_sync_error = ?, updated_at = ?
     WHERE id = ?`,
    errorMessage,
    now,
    id
  );
}
