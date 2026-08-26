import * as Location from 'expo-location';

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
  if (!isValidCoordinate(latitude, longitude)) {
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
