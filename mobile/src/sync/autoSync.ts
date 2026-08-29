import { useEffect, useRef } from 'react';
import * as Network from 'expo-network';
import type { SQLiteDatabase } from 'expo-sqlite';

import { isAutoSyncEnabled } from '../repositories/settingsRepository';
import { syncAll } from './syncService';

/**
 * Auto-sync: when the guide has opted in (see HomeScreen's toggle, backed by
 * settingsRepository), attempts the EXISTING syncAll(db) as soon as this
 * device transitions from disconnected to connected. No new sync engine, no
 * new outbox, no new upload logic — this only decides WHEN to call the sync
 * that already exists, exactly the same call HomeScreen's "Sync now" button
 * makes.
 *
 * FIRES ON ANY CONNECTIVITY, Wi-Fi or cellular — a guide in the field is
 * often on cellular data with no Wi-Fi in sight for days, and restricting
 * auto-sync to Wi-Fi-only would mean it silently never fires for them.
 * Manual "Sync now" always remains available regardless of this setting.
 *
 * syncAll(db) already de-dupes concurrent calls (see its own `syncInFlight`
 * guard) — this hook does not need its own lock. If a manual sync is already
 * running when connectivity flips, this call simply resolves to that same
 * in-flight run rather than starting a second one.
 */
export function useAutoSync(db: SQLiteDatabase): void {
  // Tracks whether the LAST known state was connected, so a sync only fires
  // on a genuine disconnected->connected transition — not on every listener
  // callback, some of which fire repeatedly for the same state.
  const wasConnected = useRef<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function maybeSync(isConnected: boolean) {
      const becameConnected = isConnected && wasConnected.current === false;
      wasConnected.current = isConnected;
      if (!becameConnected || cancelled) return;

      const enabled = await isAutoSyncEnabled(db);
      if (enabled && !cancelled) {
        syncAll(db).catch((err) => {
          // Best-effort by design: a background auto-sync failure must never
          // surface as an error the guide has to dismiss. It stays queued
          // and gets picked up by the next successful trigger, or a manual
          // "Sync now" tap — the existing failed/pending statuses already
          // carry it forward.
          console.warn('[autoSync] Background sync attempt failed:', err);
        });
      }
    }

    // Establish the starting state, then sync immediately if we're already
    // online and enabled — the most common real moment a guide expects this:
    // reopening the app back on connectivity after being offline in the
    // field, without needing a fresh disconnect/reconnect to trigger it.
    Network.getNetworkStateAsync()
      .then((state) => {
        wasConnected.current = state.isConnected ?? false;
        if (wasConnected.current) {
          return isAutoSyncEnabled(db).then((enabled) => {
            if (enabled && !cancelled) {
              syncAll(db).catch((err) => {
                console.warn('[autoSync] Initial sync attempt failed:', err);
              });
            }
          });
        }
      })
      .catch(() => {
        // Network state genuinely unknown -- leave wasConnected null so the
        // first real listener callback establishes it instead of guessing.
      });

    const subscription = Network.addNetworkStateListener((state) => {
      maybeSync(state.isConnected ?? false);
    });

    return () => {
      cancelled = true;
      subscription.remove();
    };
  }, [db]);
}
