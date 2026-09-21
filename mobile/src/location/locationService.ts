import * as Location from 'expo-location';

import { isValidCoordinatePair } from './coordinateValidation';

/** Only the fields the rest of the app actually needs — not the raw device API shape. */
export interface CapturedLocation {
  latitude: number;
  longitude: number;
  accuracyMeters: number | null;
  /** ISO-8601, timezone-aware — when the device fixed this location. */
  recordedAt: string;
}

export type LocationCaptureResult =
  | { status: 'success'; location: CapturedLocation }
  | { status: 'permission-denied'; canAskAgain: boolean }
  | { status: 'error'; message: string };

/**
 * Foreground-only, one-shot "where am I right now" capture. Requests permission
 * only if not already granted, and only as a direct result of this call — never
 * proactively. No background permission is requested or used.
 *
 * Never fabricates a result: a denied permission or a device/API failure is
 * reported as such, not silently turned into a fake or stale location.
 */
export async function captureCurrentLocation(): Promise<LocationCaptureResult> {
  let permission = await Location.getForegroundPermissionsAsync();
  if (permission.status !== Location.PermissionStatus.GRANTED) {
    permission = await Location.requestForegroundPermissionsAsync();
  }
  if (permission.status !== Location.PermissionStatus.GRANTED) {
    return { status: 'permission-denied', canAskAgain: permission.canAskAgain };
  }

  let position: Location.LocationObject;
  try {
    position = await Location.getCurrentPositionAsync();
  } catch (err) {
    console.error('[locationService] getCurrentPositionAsync failed:', err);
    return {
      status: 'error',
      message: 'Could not determine your current location. Please try again.',
    };
  }

  const { latitude, longitude, accuracy } = position.coords;
  // Real device GPS landing on exactly (0, 0) is essentially never a genuine
  // fix -- but a fake/simulator location or a device-level bug can produce
  // it, and this app treats that pair as its own missing/placeholder
  // sentinel everywhere else (see coordinateValidation.ts's module
  // docstring), so it is rejected here too rather than silently accepted as
  // a confident 'gps_live' reading.
  if (!isValidCoordinatePair(latitude, longitude)) {
    return { status: 'error', message: 'The device returned an invalid location.' };
  }

  return {
    status: 'success',
    location: {
      latitude,
      longitude,
      accuracyMeters: accuracy ?? null,
      recordedAt: new Date(position.timestamp).toISOString(),
    },
  };
}
