import { useCallback, useEffect, useState } from 'react';
import type { SQLiteDatabase } from 'expo-sqlite';

import { countAnswersByStatus } from '../repositories/answerRepository';
import { countCapturesByStatus } from '../repositories/captureRepository';
import { countLocationsByStatus } from '../repositories/locationRepository';

/**
 * Total local items (notes + voice + locations + answers) waiting to sync or
 * needing a retry, for the Activity tab badge (Step 15). Deliberately
 * excludes 'uploading' — that status is transient and would make the badge
 * flicker; this counts only items genuinely needing the guide's attention or
 * a future sync pass. Recomputed whenever `refreshKey` changes (RootNavigator
 * bumps it on returning to a tab-root screen) — cheap local SQLite reads,
 * no network.
 */
export function useLocalActivityCount(
  db: SQLiteDatabase,
  localGuideId: number | null,
  refreshKey: number
): number | null {
  const [count, setCount] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    if (localGuideId === null) {
      setCount(null);
      return;
    }
    try {
      const [notesAndVoice, locations, answers] = await Promise.all([
        countCapturesByStatus(db, localGuideId, ['pending', 'failed']),
        countLocationsByStatus(db, localGuideId, ['pending', 'failed']),
        countAnswersByStatus(db, localGuideId, ['pending', 'failed']),
      ]);
      setCount(notesAndVoice + locations + answers);
    } catch (err) {
      console.error('[useLocalActivityCount] Failed to compute activity count:', err);
      setCount(null);
    }
  }, [db, localGuideId]);

  useEffect(() => {
    refresh();
  }, [refresh, refreshKey]);

  return count;
}
