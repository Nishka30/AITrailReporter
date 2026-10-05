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
  /** JSON-encoded string array (e.g. '["BCT","HW"]'), or NULL -- see
   * decodeBrands/encodeBrands below for the only place this is parsed. */
  brands: string | null;
  profile_dirty: number;
  created_at: string;
  updated_at: string;
}

/** The sole place `brands` is parsed out of its on-disk JSON-string form.
 * Tolerant of a malformed/legacy value: treated as "no brands recorded"
 * rather than throwing and breaking the whole profile screen over one bad
 * column. */
function decodeBrands(raw: string | null): string[] | null {
  if (raw === null) return null;
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : null;
  } catch {
    return null;
  }
}

/** The sole place `brands` is serialized to its on-disk JSON-string form.
 * An empty array is stored the same as null (no brands recorded) -- this
 * repository has no "explicitly zero brands" state, matching the backend's
 * own rule that a brand-aware caller must always select at least one. */
function encodeBrands(brands: string[] | null): string | null {
  if (!brands || brands.length === 0) return null;
  return JSON.stringify(brands);
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
    brands: decodeBrands(row.brands),
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
 * Step 17: setup can now collect a phone number, an optional profile photo, an
 * optional "About you" note, and which brand(s) the guide belongs to, all at
 * the same time. `profile_dirty` is left at its default 0 deliberately — this
 * guide does not exist on the server yet, and when the sync engine creates it,
 * it sends these current values (including brands) as part of creation.
 * Marking it dirty would queue a redundant PATCH straight after.
 */
export async function createLocalGuide(
  db: SQLiteDatabase,
  name: string,
  phoneNumber: string | null = null,
  options: { aboutText?: string | null; localPhotoUri?: string | null; brands?: string[] | null } = {}
): Promise<LocalGuide> {
  const now = new Date().toISOString();
  const clientGuideId = generateClientId();
  const result = await db.runAsync(
    `INSERT INTO local_guide
       (client_guide_id, server_guide_id, name, phone_number, about_text, local_photo_uri,
        brands, profile_dirty, created_at, updated_at)
     VALUES (?, NULL, ?, ?, ?, ?, ?, 0, ?, ?)`,
    clientGuideId,
    name,
    phoneNumber,
    options.aboutText ?? null,
    options.localPhotoUri ?? null,
    encodeBrands(options.brands ?? null),
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
  /** Which brand(s) the guide belongs to -- same server-visible treatment as
   * name/phoneNumber below (see updateLocalGuideProfile's dirty check). */
  brands: string[] | null;
}

/**
 * Saves every editable profile field at once (Step 17: the Profile screen's
 * single "Save profile" action). Purely local and offline-safe — it writes to
 * SQLite and returns; it never waits on the network.
 *
 * Sets `profile_dirty = 1` when ANY server-visible field actually changed --
 * name, phoneNumber, OR brands. That precision matters: `aboutText` and
 * `localPhotoUri` never leave the device, so editing only those must not
 * queue a pointless PATCH. Comparing against the stored row (rather than
 * trusting the caller) means the flag reflects real divergence from the
 * server, not merely "the user pressed save". Brands are compared by their
 * encoded form, which is order- and content-sensitive -- sufficient here
 * since BrandSelector always produces a canonical BRAND_OPTIONS-filtered
 * order (see formatBrands) rather than an arbitrary one.
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

  const nextBrandsEncoded = encodeBrands(update.brands);
  const serverVisibleChanged =
    existing.name !== update.name ||
    existing.phone_number !== update.phoneNumber ||
    existing.brands !== nextBrandsEncoded;
  const nextDirty = existing.profile_dirty === 1 || serverVisibleChanged ? 1 : 0;

  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE local_guide
     SET name = ?, phone_number = ?, about_text = ?, local_photo_uri = ?, brands = ?,
         profile_dirty = ?, updated_at = ?
     WHERE id = ?`,
    update.name,
    update.phoneNumber,
    update.aboutText,
    update.localPhotoUri,
    nextBrandsEncoded,
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
 * name, phone number, or brands in the form above is left completely
 * untouched — a photo change must not silently commit half-finished edits.
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
 * name/phone/brands. Called by the sync engine only, never optimistically — the
 * flag staying set is what makes an interrupted push retry on the next sync.
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
