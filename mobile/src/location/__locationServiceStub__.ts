// TEST-ONLY stub, used solely by the standalone location-architecture test
// run (see __location_test__.ts / test-loader.mjs) to avoid loading the real
// expo-location -> react-native native-module chain under plain Node, which
// this project has no RN test harness for. Never imported by app code.
export type CapturedLocation = {
  latitude: number;
  longitude: number;
  accuracyMeters: number | null;
  recordedAt: string;
};
export type LocationCaptureResult =
  | { status: 'success'; location: CapturedLocation }
  | { status: 'permission-denied'; canAskAgain: boolean }
  | { status: 'error'; message: string };

export async function captureCurrentLocation(): Promise<LocationCaptureResult> {
  return { status: 'error', message: 'stubbed for the standalone test run' };
}
