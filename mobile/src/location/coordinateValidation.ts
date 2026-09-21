/**
 * The ONE canonical definition of "is this a real, usable coordinate" for a
 * contribution's own location -- mirrors
 * backend/app/services/geo_validation.py's is_valid_coordinate_pair exactly,
 * so mobile and backend agree on the rule rather than drifting apart.
 *
 * WHY THIS EXISTS: a real production incident. Two 'memory' submissions were
 * stored as exactly latitude=0, longitude=0 -- the app's OWN EXIF parser
 * (photoLocationResolver.ts) treated a zeroed EXIF GPS block (a placeholder
 * many camera/OS/photo-sharing pipelines write when there was no real GPS
 * lock, or when location metadata was stripped for privacy) as a genuine,
 * confident fix, because `0` is a perfectly finite number within
 * [-90,90]/[-180,180] -- nothing in a plain range check can tell it apart
 * from a real reading. One of those two submissions went on to carry that
 * fake coordinate onto two Observations, confirmed live in production.
 *
 * (0, 0) is mathematically the Gulf of Guinea -- never a real place any
 * guide using this app is actually reporting from -- so it is treated here
 * as this application's own "missing/placeholder" sentinel, on top of (not
 * instead of) an ordinary numeric-range check. This is checked at the
 * WRITE boundary (captureRepository.ts / answerRepository.ts), not only at
 * each individual capture site, so no current or future caller can persist
 * it by skipping a call this module doesn't itself enforce.
 */

/**
 * True only for a coordinate this application accepts as a contribution's
 * real location. False for missing, non-finite (NaN/Infinity), out-of-range,
 * or the exact placeholder pair (0, 0).
 *
 * Deliberately does NOT reject a coordinate merely because ONE component is
 * zero -- (0, 78.4) is a legitimate real-world point on the Prime Meridian.
 * Only the exact pair (0, 0) is excluded.
 */
export function isValidCoordinatePair(
  latitude: number | null | undefined,
  longitude: number | null | undefined
): latitude is number {
  if (latitude == null || longitude == null) return false;
  if (typeof latitude !== 'number' || typeof longitude !== 'number') return false;
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return false;
  if (latitude < -90 || latitude > 90) return false;
  if (longitude < -180 || longitude > 180) return false;
  if (latitude === 0 && longitude === 0) return false;
  return true;
}

/**
 * Convenience for a "have I got a real pair, or should I fall through to the
 * next location tier" decision -- returns the pair unchanged when valid, or
 * null when not (never a fabricated/clamped value). Callers that already
 * have a `{ latitude, longitude }`-shaped object commonly want this instead
 * of the raw boolean.
 */
export function sanitizeCoordinatePair(
  latitude: number | null | undefined,
  longitude: number | null | undefined
): { latitude: number; longitude: number } | null {
  if (!isValidCoordinatePair(latitude, longitude) || longitude == null) return null;
  return { latitude, longitude };
}
