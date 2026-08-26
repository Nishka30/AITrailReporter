import type { SQLiteDatabase } from 'expo-sqlite';

import { generateClientId } from '../db/uuid';
import type { LocalGuide } from '../types/models';

interface LocalGuideRow {
  id: number;
  client_guide_id: string;
  server_guide_id: string | null;
  name: string;
  phone_number: string | null;
  created_at: string;
  updated_at: string;
}

function mapRow(row: LocalGuideRow): LocalGuide {
  return {
    id: row.id,
    clientGuideId: row.client_guide_id,
    serverGuideId: row.server_guide_id,
    name: row.name,
    phoneNumber: row.phone_number,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

/**
 * Creates the local guide profile for this device, generating its stable
 * client_guide_id once. Purely local — does not call the backend and does not
 * require connectivity.
 */
export async function createLocalGuide(
  db: SQLiteDatabase,
  name: string,
  phoneNumber: string | null = null
): Promise<LocalGuide> {
  const now = new Date().toISOString();
  const clientGuideId = generateClientId();
  const result = await db.runAsync(
    `INSERT INTO local_guide (client_guide_id, server_guide_id, name, phone_number, created_at, updated_at)
     VALUES (?, NULL, ?, ?, ?, ?)`,
    clientGuideId,
    name,
    phoneNumber,
    now,
    now
  );

  const row = await db.getFirstAsync<LocalGuideRow>(
    'SELECT * FROM local_guide WHERE id = ?',
    result.lastInsertRowId
  );
  if (!row) {
    throw new Error('Failed to read back the newly created local guide profile.');
  }
  return mapRow(row);
}

/**
 * Returns the single local guide profile for this device (Step 4 assumes one
 * primary guide per device), or null if none has been set up yet.
 */
export async function getCurrentLocalGuide(db: SQLiteDatabase): Promise<LocalGuide | null> {
  const row = await db.getFirstAsync<LocalGuideRow>(
    'SELECT * FROM local_guide ORDER BY id ASC LIMIT 1'
  );
  return row ? mapRow(row) : null;
}

export async function updateLocalGuideName(
  db: SQLiteDatabase,
  id: number,
  name: string
): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync('UPDATE local_guide SET name = ?, updated_at = ? WHERE id = ?', name, now, id);
}

/**
 * Records that this guide now exists on the backend. Called by the sync engine
 * only, after POST /api/v1/guides has confirmed (created or resolved) the server
 * record for this guide's client_guide_id.
 */
export async function setServerGuideId(
  db: SQLiteDatabase,
  id: number,
  serverGuideId: string
): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    'UPDATE local_guide SET server_guide_id = ?, updated_at = ? WHERE id = ?',
    serverGuideId,
    now,
    id
  );
}
