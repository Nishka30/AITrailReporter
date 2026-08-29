import type { SQLiteDatabase } from 'expo-sqlite';

import { generateClientId } from './uuid';

export const DATABASE_NAME = 'trailreporter.db';

/**
 * Schema version, tracked via SQLite's built-in `PRAGMA user_version`.
 * Bump this and add a new `if (currentDbVersion === N)` step below whenever the
 * local schema changes — never edit an already-shipped migration step.
 */
const DATABASE_VERSION = 10;

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

  if (currentDbVersion === 6) {
    // Step 17 (Profile): the guide profile gains an optional "About you" note
    // and an optional profile photo, plus a flag tracking whether the
    // server-visible identity fields have local edits still to push.
    //
    // Purely additive nullable columns on local_guide, exactly like the v3->v4
    // and v5->v6 steps. NO BACKFILL, and none is needed:
    //   - about_text / local_photo_uri: an existing guide genuinely has neither,
    //     so NULL is the truthful value rather than a "not yet migrated" marker.
    //   - profile_dirty defaults to 0 for every existing row, which is also the
    //     truthful value: whatever name/phone they have was already sent at
    //     guide-creation time (or the guide isn't on the server yet, in which
    //     case creation will send the current values anyway). Marking existing
    //     rows dirty would queue a pointless PATCH for every upgrading install.
    //
    // Note what is NOT here: no new table, and no new columns for Explore voice
    // notes. local_capture has carried local_audio_uri / client_audio_id /
    // audio_duration_millis / audio_content_type since v4, and an 'explore' row
    // simply populates those same columns now. The existing
    // ux_local_capture_client_audio_id unique index already gives Explore voice
    // the same upload idempotency guarantee voice notes have had all along
    // (NULLs are distinct in a SQLite UNIQUE index, so rows without audio are
    // unaffected). Reusing them was the smallest correct change — a parallel
    // set of explore_audio_* columns would have duplicated the schema, the sync
    // logic, and the idempotency rules for no benefit.
    //
    // profile_dirty is INTEGER (0/1) because SQLite has no native boolean —
    // matching how the rest of this schema stores flags.
    await db.execAsync(`
      BEGIN TRANSACTION;

      ALTER TABLE local_guide ADD COLUMN about_text TEXT;
      ALTER TABLE local_guide ADD COLUMN local_photo_uri TEXT;
      ALTER TABLE local_guide ADD COLUMN profile_dirty INTEGER NOT NULL DEFAULT 0;

      COMMIT;
    `);
    currentDbVersion = 7;
  }

  if (currentDbVersion === 7) {
    // Step 18: popular questions (a SECOND question source) and reward points.
    //
    // Purely additive nullable/defaulted columns, exactly like v5->v6 and
    // v6->v7. NO BACKFILL, and none is needed:
    //   - question_kind defaults to 'dynamic', which is the TRUTHFUL value for
    //     every pre-existing local answer: before this version the only
    //     questions that existed were knowledge-gap ones. It is not a "not yet
    //     migrated" placeholder.
    //   - reward_points stays NULL on existing rows because those answers/
    //     contributions genuinely earned nothing — rewards did not exist when
    //     they were made. Inventing a retroactive number would show the guide
    //     points the backend will never actually award them.
    //
    // Note what is NOT here: no new table for popular-question answers. A
    // local answer is a local answer; `server_question_id` holds either kind
    // of id and `question_kind` says which endpoint syncService should POST
    // to. A parallel table would have duplicated the entire outbox shape, its
    // sync logic, and its idempotency rules for no benefit — the same
    // reasoning that made Explore reuse local_capture's audio columns in
    // v6->v7.
    //
    // The existing ux_local_answer_question_id unique index keeps its meaning
    // ("one local answer per question on this device") for both kinds: the two
    // id spaces are distinct server-side UUIDs.
    await db.execAsync(`
      BEGIN TRANSACTION;

      ALTER TABLE local_answer ADD COLUMN question_kind TEXT NOT NULL DEFAULT 'dynamic';
      ALTER TABLE local_answer ADD COLUMN reward_points INTEGER;
      ALTER TABLE local_capture ADD COLUMN reward_points INTEGER;

      COMMIT;
    `);
    currentDbVersion = 8;
  }

  if (currentDbVersion === 8) {
    // v8 -> v9: place-specific contribution invitations.
    //
    // Records WHICH place question an Explore contribution is answering, so the
    // backend can pay it at that question's own kind-specific rate (a photo
    // request is worth more than a status check) and so provenance survives the
    // offline queue.
    //
    // Deliberately reuses local_capture rather than adding a table. A
    // place-question contribution IS an Explore contribution — same composer,
    // same photo/voice attachments, same two-stage idempotent upload, same
    // extraction path. The only difference is which invitation prompted it,
    // which is exactly one nullable column. This is the same reasoning that put
    // Explore's audio on local_capture in v6->v7 rather than forking the outbox.
    //
    // NULL on every existing row is the truthful value: those contributions were
    // genuinely not answering a place question.
    //
    // No column is added for the contribution KIND or its point value. Both are
    // backend-owned and travel with the question itself; storing a copy here
    // would let a stale device disagree with the server about what something is
    // worth. `reward_points` (added in v8) still snapshots what the backend said
    // at the moment of answering, which is a server-issued number, not a guess.
    await db.execAsync(`
      BEGIN TRANSACTION;

      ALTER TABLE local_capture ADD COLUMN place_question_id TEXT;

      COMMIT;
    `);
    currentDbVersion = 9;
  }

  if (currentDbVersion === 9) {
    // v9 -> v10: location/date provenance for contributions, the new
    // 'memory' capture type, and a device-preferences table.
    //
    // Mirrors the backend's Submission columns exactly (see
    // backend/app/db/models/submission.py's SUBMISSION_LOCATION_SOURCES /
    // DATE_PRECISIONS / DATE_SOURCES) so syncService can pass these straight
    // through on POST /api/v1/submissions with no local re-interpretation.
    //
    // `latitude`/`longitude` are new HERE on local_capture: until this
    // release no capture type carried its own coordinate at all (Explore's
    // "you're here" context always came from the separate live GuideLocation
    // pings in local_location, never from the capture row itself). A photo's
    // EXIF GPS or a live-captured note's device GPS now can.
    //
    // Existing rows get the honest defaults ('unknown'/NULL) rather than a
    // backfilled guess — a capture made before this column existed genuinely
    // has no recorded provenance, and pretending otherwise would be exactly
    // the kind of fabricated confidence this feature exists to prevent.
    await db.execAsync(`
      BEGIN TRANSACTION;

      ALTER TABLE local_capture ADD COLUMN latitude REAL;
      ALTER TABLE local_capture ADD COLUMN longitude REAL;
      ALTER TABLE local_capture ADD COLUMN location_source TEXT NOT NULL DEFAULT 'unknown';
      ALTER TABLE local_capture ADD COLUMN location_accuracy_meters REAL;
      ALTER TABLE local_capture ADD COLUMN location_captured_at TEXT;
      ALTER TABLE local_capture ADD COLUMN location_label TEXT;
      ALTER TABLE local_capture ADD COLUMN location_evidence TEXT;
      ALTER TABLE local_capture ADD COLUMN occurred_at TEXT;
      ALTER TABLE local_capture ADD COLUMN occurred_at_precision TEXT NOT NULL DEFAULT 'unknown';
      ALTER TABLE local_capture ADD COLUMN date_source TEXT NOT NULL DEFAULT 'unknown';

      -- Device-level preferences (e.g. auto-sync). Deliberately NOT a column
      -- on local_guide: this is a property of the install, not of a person,
      -- and switching the active guide on one device should not reset it.
      CREATE TABLE IF NOT EXISTS local_settings (
        key TEXT PRIMARY KEY NOT NULL,
        value TEXT NOT NULL
      );

      COMMIT;
    `);
    currentDbVersion = 10;
  }

  // Future schema changes: add `if (currentDbVersion === 10) { ...; currentDbVersion = 11; }`

  await db.execAsync(`PRAGMA user_version = ${currentDbVersion}`);
}
