import type { SQLiteDatabase } from 'expo-sqlite';

import { generateClientId } from '../db/uuid';
import type { LocalGuide } from '../types/models';

interface LocalGuideRow {
  id: number;
  client_guide_id: string;
  server_guide_id: string | null;
  name: string;
  phone_number: string | null;
  about_text: string | null;
  local_photo_uri: string | null;
  profile_dirty: number;
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
    aboutText: row.about_text,
    localPhotoUri: row.local_photo_uri,
    // SQLite has no boolean type — 0/1 is the storage shape, `boolean` is the
    // shape the rest of the app reasons about.
    profileDirty: row.profile_dirty === 1,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

/**
 * Creates the local guide profile for this device, generating its stable
 * client_guide_id once. Purely local — does not call the backend and does not
 * require connectivity.
 *
 * Step 17: setup can now collect a phone number, an optional profile photo and
 * an optional "About you" note at the same time. `profile_dirty` is left at its
 * default 0 deliberately — this guide does not exist on the server yet, and
 * when the sync engine creates it, it sends these current values as part of
 * creation. Marking it dirty would queue a redundant PATCH straight after.
 */
export async function createLocalGuide(
  db: SQLiteDatabase,
  name: string,
  phoneNumber: string | null = null,
  options: { aboutText?: string | null; localPhotoUri?: string | null } = {}
): Promise<LocalGuide> {
  const now = new Date().toISOString();
  const clientGuideId = generateClientId();
  const result = await db.runAsync(
    `INSERT INTO local_guide
       (client_guide_id, server_guide_id, name, phone_number, about_text, local_photo_uri,
        profile_dirty, created_at, updated_at)
     VALUES (?, NULL, ?, ?, ?, ?, 0, ?, ?)`,
    clientGuideId,
    name,
    phoneNumber,
    options.aboutText ?? null,
    options.localPhotoUri ?? null,
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

export interface ProfileUpdate {
  name: string;
  phoneNumber: string | null;
  aboutText: string | null;
  localPhotoUri: string | null;
}

/**
 * Saves every editable profile field at once (Step 17: the Profile screen's
 * single "Save profile" action). Purely local and offline-safe — it writes to
 * SQLite and returns; it never waits on the network.
 *
 * Sets `profile_dirty = 1` ONLY when a server-visible field actually changed.
 * That precision matters: `aboutText` and `localPhotoUri` never leave the
 * device, so editing only those must not queue a pointless PATCH. Comparing
 * against the stored row (rather than trusting the caller) means the flag
 * reflects real divergence from the server, not merely "the user pressed save".
 *
 * The flag is sticky — an edit made while a previous edit is still unsynced
 * keeps it set, and only a confirmed push clears it (see markProfileSynced).
 */
export async function updateLocalGuideProfile(
  db: SQLiteDatabase,
  id: number,
  update: ProfileUpdate
): Promise<LocalGuide> {
  const existing = await db.getFirstAsync<LocalGuideRow>(
    'SELECT * FROM local_guide WHERE id = ?',
    id
  );
  if (!existing) {
    throw new Error('Cannot update a guide profile that does not exist on this device.');
  }

  const serverVisibleChanged =
    existing.name !== update.name || existing.phone_number !== update.phoneNumber;
  const nextDirty = existing.profile_dirty === 1 || serverVisibleChanged ? 1 : 0;

  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_guide
     SET name = ?, phone_number = ?, about_text = ?, local_photo_uri = ?,
         profile_dirty = ?, updated_at = ?
     WHERE id = ?`,
    update.name,
    update.phoneNumber,
    update.aboutText,
    update.localPhotoUri,
    nextDirty,
    now,
    id
  );

  const row = await db.getFirstAsync<LocalGuideRow>('SELECT * FROM local_guide WHERE id = ?', id);
  if (!row) {
    throw new Error('Failed to read back the updated local guide profile.');
  }
  return mapRow(row);
}

/**
 * Saves ONLY the profile photo, immediately.
 *
 * Separate from updateLocalGuideProfile above because a profile photo is not
 * like the other fields: it never leaves the device, so there is nothing to
 * validate and nothing to push, and deferring it behind the "Save profile"
 * button was an actual bug — picking a photo updated the avatar instantly,
 * which reads as "saved", but navigating back discarded it and left the copied
 * file orphaned on disk.
 *
 * Deliberately touches no other column and NEVER sets profile_dirty: the photo
 * is not a server-visible field, so changing it must not queue a profile PATCH.
 * Writing only this one column also means an in-progress, unsaved edit to the
 * name or phone number in the form above is left completely untouched — a
 * photo change must not silently commit half-typed text.
 */
export async function updateLocalGuidePhoto(
  db: SQLiteDatabase,
  id: number,
  localPhotoUri: string | null
): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    'UPDATE local_guide SET local_photo_uri = ?, updated_at = ? WHERE id = ?',
    localPhotoUri,
    now,
    id
  );
}

/**
 * Clears the pending-profile-push flag after the backend has CONFIRMED the new
 * name/phone. Called by the sync engine only, never optimistically — the flag
 * staying set is what makes an interrupted push retry on the next sync.
 */
export async function markProfileSynced(db: SQLiteDatabase, id: number): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    'UPDATE local_guide SET profile_dirty = 0, updated_at = ? WHERE id = ?',
    now,
    id
  );
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
