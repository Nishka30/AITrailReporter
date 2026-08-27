import type { SQLiteDatabase } from 'expo-sqlite';

import { generateClientId } from './uuid';

export const DATABASE_NAME = 'trailreporter.db';

/**
 * Schema version, tracked via SQLite's built-in `PRAGMA user_version`.
 * Bump this and add a new `if (currentDbVersion === N)` step below whenever the
 * local schema changes — never edit an already-shipped migration step.
 */
const DATABASE_VERSION = 6;

/**
 * Called once by <SQLiteProvider onInit={migrateDbIfNeeded}> the first time the
 * database is opened. Every step uses CREATE TABLE IF NOT EXISTS / additive changes
 * only — reopening the app never drops or resets existing data.
 */
export async function migrateDbIfNeeded(db: SQLiteDatabase): Promise<void> {
  const row = await db.getFirstAsync<{ user_version: number }>('PRAGMA user_version');
  let currentDbVersion = row?.user_version ?? 0;

  if (currentDbVersion >= DATABASE_VERSION) {
    return;
  }

  if (currentDbVersion === 0) {
    await db.execAsync('PRAGMA journal_mode = WAL');
    await db.execAsync(`
      BEGIN TRANSACTION;

      CREATE TABLE IF NOT EXISTS local_guide (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_guide_id TEXT,
        name TEXT NOT NULL,
        phone_number TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS local_capture (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        local_guide_id INTEGER NOT NULL REFERENCES local_guide(id),
        capture_type TEXT NOT NULL,
        text_content TEXT,
        sync_status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );

      CREATE INDEX IF NOT EXISTS idx_local_capture_guide_id
        ON local_capture (local_guide_id);

      COMMIT;
    `);
    currentDbVersion = 1;
  }

  if (currentDbVersion === 1) {
    // Adds the stable client-generated identifiers and sync bookkeeping columns
    // needed for the outbox sync (Step 5). Purely additive — no existing column is
    // touched or dropped, so pre-existing local_guide/local_capture rows survive.
    await db.withExclusiveTransactionAsync(async (txn) => {
      await txn.execAsync(`
        ALTER TABLE local_guide ADD COLUMN client_guide_id TEXT;
        ALTER TABLE local_capture ADD COLUMN client_submission_id TEXT;
        ALTER TABLE local_capture ADD COLUMN server_submission_id TEXT;
        ALTER TABLE local_capture ADD COLUMN last_sync_error TEXT;
        ALTER TABLE local_capture ADD COLUMN sync_attempt_count INTEGER NOT NULL DEFAULT 0;
      `);

      // Backfill a stable client id for any row that predates this column (Step 4
      // data). Generated exactly once per row, here — never regenerated afterwards.
      const guidesNeedingId = await txn.getAllAsync<{ id: number }>(
        'SELECT id FROM local_guide WHERE client_guide_id IS NULL'
      );
      for (const row of guidesNeedingId) {
        await txn.runAsync(
          'UPDATE local_guide SET client_guide_id = ? WHERE id = ?',
          generateClientId(),
          row.id
        );
      }

      const capturesNeedingId = await txn.getAllAsync<{ id: number }>(
        'SELECT id FROM local_capture WHERE client_submission_id IS NULL'
      );
      for (const row of capturesNeedingId) {
        await txn.runAsync(
          'UPDATE local_capture SET client_submission_id = ? WHERE id = ?',
          generateClientId(),
          row.id
        );
      }

      // Enforced only after backfill, so every existing row already has a value.
      await txn.execAsync(`
        CREATE UNIQUE INDEX IF NOT EXISTS ux_local_guide_client_guide_id
          ON local_guide (client_guide_id);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_local_capture_client_submission_id
          ON local_capture (client_submission_id);
      `);
    });
    currentDbVersion = 2;
  }

  if (currentDbVersion === 2) {
    // A brand-new table (Step 6: GPS capture) — every row created from here on
    // already has a client_location_id at insert time, so unlike the v1->v2 step
    // there's no pre-existing data to backfill.
    await db.execAsync(`
      BEGIN TRANSACTION;

      CREATE TABLE IF NOT EXISTS local_location (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        local_guide_id INTEGER NOT NULL REFERENCES local_guide(id),
        client_location_id TEXT NOT NULL,
        server_location_id TEXT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        accuracy_meters REAL,
        recorded_at TEXT NOT NULL,
        sync_status TEXT NOT NULL DEFAULT 'pending',
        sync_attempt_count INTEGER NOT NULL DEFAULT 0,
        last_sync_error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );

      CREATE UNIQUE INDEX IF NOT EXISTS ux_local_location_client_location_id
        ON local_location (client_location_id);

      CREATE INDEX IF NOT EXISTS idx_local_location_guide_status
        ON local_location (local_guide_id, sync_status);

      CREATE INDEX IF NOT EXISTS idx_local_location_guide_recorded_at
        ON local_location (local_guide_id, recorded_at);

      COMMIT;
    `);
    currentDbVersion = 3;
  }

  if (currentDbVersion === 3) {
    // Adds audio-capture metadata to the existing local_capture table (Step 7:
    // voice observations). Purely additive nullable columns — 'note' and
    // 'location' rows never populate them, so nothing existing changes shape.
    // Unlike the v1->v2 step, no backfill is needed: these columns are only ever
    // set for newly-created 'voice' rows going forward, so every pre-existing row
    // correctly stays NULL forever (not "not yet backfilled").
    await db.execAsync(`
      BEGIN TRANSACTION;

      ALTER TABLE local_capture ADD COLUMN local_audio_uri TEXT;
      ALTER TABLE local_capture ADD COLUMN client_audio_id TEXT;
      ALTER TABLE local_capture ADD COLUMN audio_duration_millis INTEGER;
      ALTER TABLE local_capture ADD COLUMN audio_content_type TEXT;

      CREATE UNIQUE INDEX IF NOT EXISTS ux_local_capture_client_audio_id
        ON local_capture (client_audio_id);

      COMMIT;
    `);
    currentDbVersion = 4;
  }

  if (currentDbVersion === 4) {
    // A brand-new table (Step 13: guide answers to assigned questions) — every
    // row created from here on already has a client_answer_id at insert time,
    // so like the v2->v3 step there's no pre-existing data to backfill.
    // `server_question_id` is UNIQUE: at most one local answer per question,
    // matching the backend's one-answer-per-assignment-completion semantics
    // (see backend/app/services/question_answers.py) — the UI must not let a
    // guide create a second local answer for a question already answered
    // locally.
    await db.execAsync(`
      BEGIN TRANSACTION;

      CREATE TABLE IF NOT EXISTS local_answer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        local_guide_id INTEGER NOT NULL REFERENCES local_guide(id),
        server_question_id TEXT NOT NULL,
        client_answer_id TEXT NOT NULL,
        server_answer_id TEXT,
        answer_text TEXT NOT NULL,
        answered_at TEXT NOT NULL,
        sync_status TEXT NOT NULL DEFAULT 'pending',
        sync_attempt_count INTEGER NOT NULL DEFAULT 0,
        last_sync_error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );

      CREATE UNIQUE INDEX IF NOT EXISTS ux_local_answer_client_answer_id
        ON local_answer (client_answer_id);

      CREATE UNIQUE INDEX IF NOT EXISTS ux_local_answer_question_id
        ON local_answer (server_question_id);

      CREATE INDEX IF NOT EXISTS idx_local_answer_guide_status
        ON local_answer (local_guide_id, sync_status);

      COMMIT;
    `);
    currentDbVersion = 5;
  }

  if (currentDbVersion === 5) {
    // Step 16 (Explore): photo attachment metadata on the existing
    // local_capture table, plus the prompt provenance for an Explore
    // contribution. Purely additive nullable columns, exactly like the v3->v4
    // audio step — 'note'/'voice'/'location' rows never populate them, so no
    // existing row changes shape and NO BACKFILL IS NEEDED (a capture that
    // predates Explore genuinely has no photo and no prompt; NULL is the
    // truthful value, not a "not yet migrated" placeholder).
    //
    // The unique index on client_photo_id is safe to create immediately
    // precisely BECAUSE no existing row has a value: SQLite treats NULLs as
    // distinct in a UNIQUE index, so every pre-existing row trivially
    // satisfies it. (Contrast the v1->v2 step, which had to backfill ids
    // before its unique indexes could be created.)
    //
    // explore_prompt_id / explore_prompt_title record WHICH discovery prompt
    // the guide was answering. Stored locally only — the backend receives the
    // contribution as an 'explore' submission and does not model prompts (see
    // backend/README.md); this exists so the Activity/Explore UI can honestly
    // show what was asked, not to drive any server behavior.
    await db.execAsync(`
      BEGIN TRANSACTION;

      ALTER TABLE local_capture ADD COLUMN local_photo_uri TEXT;
      ALTER TABLE local_capture ADD COLUMN client_photo_id TEXT;
      ALTER TABLE local_capture ADD COLUMN photo_content_type TEXT;
      ALTER TABLE local_capture ADD COLUMN explore_prompt_id TEXT;
      ALTER TABLE local_capture ADD COLUMN explore_prompt_title TEXT;

      CREATE UNIQUE INDEX IF NOT EXISTS ux_local_capture_client_photo_id
        ON local_capture (client_photo_id);

      COMMIT;
    `);
    currentDbVersion = 6;
  }

  // Future schema changes: add `if (currentDbVersion === 6) { ...; currentDbVersion = 7; }`

  await db.execAsync(`PRAGMA user_version = ${currentDbVersion}`);
}
