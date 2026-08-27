import { useCallback, useState } from 'react';

/**
 * Drives a `<RefreshControl>` from ONLY genuine user pulls.
 *
 * Why this exists: every list screen already has a `loading` flag covering all
 * of its data loads — mount, tab re-entry (`refreshKey`), and retries. Wiring
 * that same flag straight into `refreshing` meant Android drew the pull-to-
 * refresh spinner for loads the user never asked for, so the indicator flashed
 * at the top of the screen on every tab switch. When the backend was slow or
 * unreachable (requests run to a 20s timeout — see api/client.ts) those flashes
 * were long and repeated, which reads as a spinner blinking on its own.
 *
 * Keeping the two concepts separate fixes that: this hook's `pulling` is true
 * only between the user releasing a pull gesture and that refresh settling.
 * Background loads still render each screen's own inline loading UI, which is
 * the honest place for them.
 *
 * `pulling` is always released in a `finally`, so a failed refresh can never
 * leave the spinner stuck on screen.
 */
export function usePullToRefresh(refresh: () => Promise<void> | void) {
  const [pulling, setPulling] = useState(false);

  const onPull = useCallback(async () => {
    setPulling(true);
    try {
      await refresh();
    } finally {
      setPulling(false);
    }
  }, [refresh]);

  return { pulling, onPull };
}
