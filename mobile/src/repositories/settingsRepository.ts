import type { SQLiteDatabase } from 'expo-sqlite';

import type { AppSettingKey } from '../types/models';

/**
 * Device-level app preferences (see `local_settings` in src/db/database.ts,
 * v9->v10). Deliberately a plain key/value store rather than typed columns —
 * the only setting today is auto-sync, and a second one should never need
 * its own migration.
 */

export async function getSetting(db: SQLiteDatabase, key: AppSettingKey): Promise<string | null> {
  const row = await db.getFirstAsync<{ value: string }>(
    'SELECT value FROM local_settings WHERE key = ?',
    key
  );
  return row?.value ?? null;
}

export async function setSetting(db: SQLiteDatabase, key: AppSettingKey, value: string): Promise<void> {
  await db.runAsync(
    `INSERT INTO local_settings (key, value) VALUES (?, ?)
     ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
    key,
    value
  );
}

/** Defaults to OFF: auto-sync means the app makes network requests without an
 * explicit tap, which should be something a guide opts INTO, not a behaviour
 * change existing installs wake up to. Manual "Sync now" always remains
 * available regardless of this setting. */
export async function isAutoSyncEnabled(db: SQLiteDatabase): Promise<boolean> {
  const value = await getSetting(db, 'auto_sync_enabled');
  return value === '1';
}

export async function setAutoSyncEnabled(db: SQLiteDatabase, enabled: boolean): Promise<void> {
  await setSetting(db, 'auto_sync_enabled', enabled ? '1' : '0');
}
