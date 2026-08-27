/**
 * Shared duration formatting for recorded audio (Step 17).
 *
 * Extracted because three separate places were formatting milliseconds by hand
 * — the Home voice card, the Activity list, and now the Explore voice composer
 * — and they disagreed about the unknown case. One rule, one place.
 */

/** `m:ss`, e.g. `0:07` or `2:41`. */
export function formatDurationMillis(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '0:00';
  return formatDurationSeconds(ms / 1000);
}

/** Same format, for the seconds-based values expo-audio's player reports. */
export function formatDurationSeconds(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '0:00';
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${String(secs).padStart(2, '0')}`;
}

/**
 * For places that must be honest about a duration expo-audio could not report,
 * rather than showing a confident "0:00" that looks like an empty recording.
 * Used by the Activity list, where the recording is already saved and a wrong
 * number would misdescribe stored data.
 */
export function formatDurationOrUnknown(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return 'duration unknown';
  return formatDurationMillis(ms);
}
