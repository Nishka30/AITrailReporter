import type { CaptureProvenanceInput } from '../repositories/captureRepository';
import type { PhotoPickResult } from '../photo/photoPickerService';
import { captureCurrentLocation } from './locationService';

/**
 * Turns a picked photo's raw EXIF (plus whether it came from the camera or
 * the library) into location/date PROVENANCE — never into a coordinate that
 * wasn't actually determinable.
 *
 * THE DECISION TREE, and why it's structured this way:
 *
 *   1. EXIF GPS present -> use it. Tied to the pixels themselves; the
 *      strongest evidence this app can have. `location_captured_at` comes
 *      from the EXIF GPS timestamp when present (true UTC), else is left
 *      unset rather than guessed.
 *
 *   2. No EXIF GPS, but this is a LIVE capture (camera, not library) -> read
 *      CURRENT device GPS. This branch exists specifically because of a
 *      documented Expo/iOS platform gap: iOS never includes GPS tags in EXIF
 *      for an in-app camera photo, even with location permission granted
 *      (Android and library picks are unaffected). Without this fallback,
 *      every live iOS photo would silently have NO location at all.
 *
 *   3. Neither -> return 'unknown' with whatever date evidence EXIF offered.
 *      CRITICALLY, this is the branch a library pick of an old photo with no
 *      GPS falls into, and it must NEVER read current device GPS — that
 *      guide could be nowhere near where the photo was actually taken. The
 *      backend's historical-inference step (matching occurred_at against the
 *      guide's own past GuideLocation history) is what has a chance of
 *      filling this in later, server-side, from real evidence — never
 *      guessed here on-device.
 *
 * KNOWN LIMITATION (stated plainly, not hidden): EXIF's DateTimeOriginal tag
 * has no timezone. When only that tag is available (no GPS-derived UTC
 * timestamp), this treats it as a naive local timestamp in the DEVICE's
 * current timezone — a reasonable heuristic for a guide viewing/uploading
 * their own recent photo, but not a guaranteed-correct instant if the photo
 * was taken somewhere with a different UTC offset than wherever this device
 * currently is. Because that uncertainty is real, occurred_at_precision is
 * downgraded to 'approximate' rather than 'exact' whenever the timestamp
 * came from DateTimeOriginal alone (see below) — the precision field is
 * honest about what is and isn't actually known.
 */

interface ExifDerived {
  latitude: number | null;
  longitude: number | null;
  /** ISO-8601 UTC when derivable; otherwise null even if a date WAS found
   * (see `dateIsApproximate` for the "found but uncertain" case). */
  occurredAt: string | null;
  dateIsApproximate: boolean;
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return null;
}

/**
 * EXIF GPS coordinates arrive in different shapes depending on platform/OS
 * version — Expo's docs describe the `exif` object only as "tag name ->
 * value" without enumerating the exact per-platform representation. Handles
 * both a plain decimal-degrees number (observed on iOS's ImageIO GPS
 * dictionary) and a [degrees, minutes, seconds] triple (the raw EXIF wire
 * format some Android readers pass through unconverted).
 */
function coerceGpsComponent(value: unknown): number | null {
  const asNumber = toNumber(value);
  if (asNumber !== null) return asNumber;

  if (Array.isArray(value) && value.length === 3) {
    const [deg, min, sec] = value.map(toNumber);
    if (deg === null || min === null || sec === null) return null;
    return deg + min / 60 + sec / 3600;
  }
  return null;
}

function applyHemisphere(magnitude: number | null, ref: unknown): number | null {
  if (magnitude === null) return null;
  const refStr = typeof ref === 'string' ? ref.trim().toUpperCase() : '';
  return refStr === 'S' || refStr === 'W' ? -Math.abs(magnitude) : Math.abs(magnitude);
}

function isValidCoordinate(latitude: number, longitude: number): boolean {
  return (
    Number.isFinite(latitude) &&
    Number.isFinite(longitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    longitude >= -180 &&
    longitude <= 180
  );
}

/** Parses EXIF's "YYYY:MM:DD HH:MM:SS" into components, or null if the shape
 * doesn't match. Deliberately strict: a malformed tag is treated as absent,
 * never partially guessed at. */
function parseExifDateTime(value: unknown): { y: number; mo: number; d: number; h: number; mi: number; s: number } | null {
  if (typeof value !== 'string') return null;
  const match = value
    .trim()
    .match(/^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/);
  if (!match) return null;
  const [, y, mo, d, h, mi, s] = match.map(Number) as unknown as number[];
  return { y, mo, d, h, mi, s };
}

function deriveFromExif(exif: Record<string, unknown> | null): ExifDerived {
  if (!exif) {
    return { latitude: null, longitude: null, occurredAt: null, dateIsApproximate: false };
  }

  const rawLat = coerceGpsComponent(exif.GPSLatitude);
  const rawLon = coerceGpsComponent(exif.GPSLongitude);
  const latitude = applyHemisphere(rawLat, exif.GPSLatitudeRef);
  const longitude = applyHemisphere(rawLon, exif.GPSLongitudeRef);
  const hasGps = latitude !== null && longitude !== null && isValidCoordinate(latitude, longitude);

  // Preferred: GPSDateStamp ("YYYY:MM:DD") + GPSTimeStamp ([H, M, S], UTC per
  // the EXIF spec) — an unambiguous UTC instant, present only alongside a
  // real GPS fix.
  const gpsDate = typeof exif.GPSDateStamp === 'string' ? exif.GPSDateStamp.match(/^(\d{4}):(\d{2}):(\d{2})/) : null;
  const gpsTime = Array.isArray(exif.GPSTimeStamp) ? exif.GPSTimeStamp.map(toNumber) : null;
  if (gpsDate && gpsTime && gpsTime.every((n) => n !== null)) {
    const [, y, mo, d] = gpsDate.map(Number);
    const [h, mi, s] = gpsTime as number[];
    const iso = new Date(Date.UTC(y, mo - 1, d, h, mi, Math.floor(s))).toISOString();
    return { latitude, longitude, occurredAt: iso, dateIsApproximate: false };
  }

  // Fallback: DateTimeOriginal, the camera's own local clock with NO
  // timezone recorded. Treated as this device's current local time zone —
  // see the module header's "known limitation" note.
  const local = parseExifDateTime(exif.DateTimeOriginal ?? exif.DateTime);
  if (local) {
    const iso = new Date(local.y, local.mo - 1, local.d, local.h, local.mi, local.s).toISOString();
    return { latitude, longitude, occurredAt: iso, dateIsApproximate: true };
  }

  return { latitude: hasGps ? latitude : null, longitude: hasGps ? longitude : null, occurredAt: null, dateIsApproximate: false };
}

/**
 * Resolves full location/date provenance for a successfully-picked photo.
 * Never throws — a failure to read GPS is a normal, expected outcome (most
 * photos have none), reported as `locationSource: 'unknown'`, not an error.
 */
export async function resolvePhotoProvenance(
  pick: Extract<PhotoPickResult, { status: 'success' }>
): Promise<CaptureProvenanceInput> {
  const exifResult = deriveFromExif(pick.exif);

  if (exifResult.latitude !== null && exifResult.longitude !== null) {
    return {
      latitude: exifResult.latitude,
      longitude: exifResult.longitude,
      locationSource: 'photo_exif',
      locationCapturedAt: exifResult.occurredAt,
      occurredAt: exifResult.occurredAt,
      occurredAtPrecision: exifResult.occurredAt ? (exifResult.dateIsApproximate ? 'approximate' : 'exact') : 'unknown',
      dateSource: exifResult.occurredAt ? 'exif' : 'unknown',
    };
  }

  if (pick.source === 'camera') {
    // Live capture with no EXIF GPS (the expected iOS case) -> fall back to
    // current device GPS. This is genuinely "where the guide is right now",
    // which is correct BECAUSE this is a live camera photo, not an upload.
    const live = await captureCurrentLocation();
    if (live.status === 'success') {
      return {
        latitude: live.location.latitude,
        longitude: live.location.longitude,
        locationSource: 'gps_live',
        locationAccuracyMeters: live.location.accuracyMeters,
        locationCapturedAt: live.location.recordedAt,
        occurredAt: exifResult.occurredAt ?? live.location.recordedAt,
        // 'exact' unless the only date evidence was EXIF's timezone-less
        // DateTimeOriginal (see the module header's known limitation) — in
        // every other case (no EXIF date at all, so this IS the capture
        // instant; or a GPS-timestamp-corroborated EXIF date) the instant is
        // genuinely known exactly.
        occurredAtPrecision: exifResult.occurredAt && exifResult.dateIsApproximate ? 'approximate' : 'exact',
        dateSource: exifResult.occurredAt ? 'exif' : 'device',
      };
    }
    // Permission denied or a device error: still a live capture happening
    // right now, so occurred_at is exact even though location isn't known.
    return {
      locationSource: 'unknown',
      occurredAt: new Date().toISOString(),
      occurredAtPrecision: 'exact',
      dateSource: 'device',
    };
  }

  // A library pick with no EXIF GPS: never read current GPS here (see the
  // module header). Whatever date evidence EXIF offered survives; location
  // stays honestly unknown until/unless the backend's historical-inference
  // step can establish one from the guide's own past GPS history.
  return {
    locationSource: 'unknown',
    occurredAt: exifResult.occurredAt,
    occurredAtPrecision: exifResult.occurredAt ? (exifResult.dateIsApproximate ? 'approximate' : 'exact') : 'unknown',
    dateSource: exifResult.occurredAt ? 'exif' : 'unknown',
  };
}
