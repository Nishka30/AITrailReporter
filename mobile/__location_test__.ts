/**
 * Runs the REAL mobile TypeScript (not a reimplementation) against the
 * exact spec cases, via `npx tsx`. Covers:
 *   - coordinateValidation.ts: every valid/invalid case from the spec
 *   - photoLocationResolver.ts::resolvePhotoProvenance: the actual
 *     production bug (zeroed EXIF GPS) and its fix, plus every EXIF edge
 *     case the audit asked for -- exercised through the real decision tree,
 *     not a mock of it.
 */
// expo-location (transitively imported by photoLocationResolver -> locationService)
// bootstraps RN/Expo globals (__DEV__) that plain Node does not define --
// set it before the dynamic import below so the load-time check passes.
// The library-pick scenarios this file exercises never actually CALL
// captureCurrentLocation() at runtime, so no native module is invoked.
(globalThis as any).__DEV__ = false;
import type { PhotoPickResult } from './src/photo/photoPickerService';

let failures = 0;
function check(label: string, cond: boolean, extra: string = ''): void {
  console.log(`[${cond ? 'PASS' : 'FAIL'}] ${label} ${extra}`);
  if (!cond) failures++;
}

function libraryPick(exif: Record<string, unknown> | null): Extract<PhotoPickResult, { status: 'success' }> {
  return { status: 'success', uri: 'file://test.jpg', contentType: 'image/jpeg', source: 'library', exif };
}

async function run() {
  const { isValidCoordinatePair, sanitizeCoordinatePair } = await import('./src/location/coordinateValidation');
  const { resolvePhotoProvenance } = await import('./src/location/photoLocationResolver');

  // ---------------------------------------------------------------------
  console.log('=== coordinateValidation.ts -- every specified case ===');
  const CASES: [number | null, number | null, boolean, string][] = [
    [17.45204, 78.399786, true, 'real Hyderabad coordinate'],
    [0, 78.4, true, 'lat=0 alone is valid'],
    [-0.5, 77.2, true, 'near-zero lat, valid'],
    [90, 180, true, 'max boundary'],
    [-90, -180, true, 'min boundary'],
    [0, 0, false, 'THE placeholder pair'],
    [null, null, false, 'missing'],
    [null, 78.4, false, 'lat missing'],
    [17.4, null, false, 'lon missing'],
    [NaN, 78.4, false, 'NaN'],
    [Infinity, 78.4, false, 'Infinity'],
    [91, 78.4, false, 'lat > 90'],
    [-91, 78.4, false, 'lat < -90'],
    [17.4, 181, false, 'lon > 180'],
    [17.4, -181, false, 'lon < -180'],
  ];
  for (const [lat, lon, expected, note] of CASES) {
    const got = isValidCoordinatePair(lat, lon);
    check(`(${lat}, ${lon}) -> ${expected}`, got === expected, `[${note}]`);
  }
  check('sanitizeCoordinatePair returns null for (0,0)', sanitizeCoordinatePair(0, 0) === null);
  check(
    'sanitizeCoordinatePair returns the pair unchanged for (0, 78.4)',
    JSON.stringify(sanitizeCoordinatePair(0, 78.4)) === JSON.stringify({ latitude: 0, longitude: 78.4 })
  );

  // ---------------------------------------------------------------------
  console.log('\n=== photoLocationResolver.ts::resolvePhotoProvenance -- the real EXIF decision tree ===');

  // THE production bug: a zeroed EXIF GPS block (what several camera/OS/
  // sharing pipelines write as a "no real GPS lock" placeholder).
  const zeroed = await resolvePhotoProvenance(
    libraryPick({ GPSLatitude: 0, GPSLongitude: 0, GPSLatitudeRef: 'N', GPSLongitudeRef: 'E' })
  );
  check(
    'zeroed EXIF GPS (0,0) is treated as MISSING, not a confident fix',
    zeroed.locationSource === 'unknown' && zeroed.latitude == null && zeroed.longitude == null,
    `(got locationSource=${zeroed.locationSource}, lat=${zeroed.latitude}, lon=${zeroed.longitude})`
  );

  // The SAME zeroed block, but with a genuine GPS timestamp alongside it --
  // this is the branch the original bug did NOT gate on hasGps at all.
  const zeroedWithTimestamp = await resolvePhotoProvenance(
    libraryPick({
      GPSLatitude: 0, GPSLongitude: 0, GPSLatitudeRef: 'N', GPSLongitudeRef: 'E',
      GPSDateStamp: '2026:09:17', GPSTimeStamp: [8, 16, 53],
    })
  );
  check(
    'zeroed EXIF GPS is rejected EVEN with a real GPS timestamp alongside it',
    zeroedWithTimestamp.latitude == null && zeroedWithTimestamp.longitude == null,
    `(got lat=${zeroedWithTimestamp.latitude}, lon=${zeroedWithTimestamp.longitude})`
  );
  check(
    'the genuine timestamp survives even though the location did not',
    zeroedWithTimestamp.occurredAt === new Date(Date.UTC(2026, 8, 17, 8, 16, 53)).toISOString(),
    `(got ${zeroedWithTimestamp.occurredAt})`
  );

  // A valid EXIF GPS fix must still work -- the fix must not overcorrect.
  const valid = await resolvePhotoProvenance(
    libraryPick({ GPSLatitude: 17.45204, GPSLongitude: 78.399786, GPSLatitudeRef: 'N', GPSLongitudeRef: 'E' })
  );
  check(
    'a VALID EXIF GPS fix is still accepted (no overcorrection)',
    valid.locationSource === 'photo_exif' && valid.latitude === 17.45204 && valid.longitude === 78.399786,
    `(got locationSource=${valid.locationSource}, lat=${valid.latitude}, lon=${valid.longitude})`
  );

  // A coordinate with exactly ONE zero component must NOT be rejected.
  const oneZero = await resolvePhotoProvenance(
    libraryPick({ GPSLatitude: 0, GPSLongitude: 78.4, GPSLatitudeRef: 'N', GPSLongitudeRef: 'E' })
  );
  check(
    '(0, 78.4) -- one zero component -- is accepted as valid, not rejected',
    oneZero.locationSource === 'photo_exif' && oneZero.latitude === 0 && oneZero.longitude === 78.4,
    `(got locationSource=${oneZero.locationSource}, lat=${oneZero.latitude}, lon=${oneZero.longitude})`
  );

  // Missing EXIF entirely.
  const missing = await resolvePhotoProvenance(libraryPick(null));
  check('missing EXIF -> unknown, no crash', missing.locationSource === 'unknown');

  // EXIF present but no GPS tags at all.
  const noGpsTags = await resolvePhotoProvenance(libraryPick({ Make: 'Apple', Model: 'iPhone' }));
  check('EXIF with no GPS tags -> unknown, no crash', noGpsTags.locationSource === 'unknown');

  // Partial GPS (latitude only, no longitude) -- must not half-accept.
  const partial = await resolvePhotoProvenance(
    libraryPick({ GPSLatitude: 17.45204, GPSLatitudeRef: 'N' })
  );
  check(
    'partial GPS (lat only) is rejected, not half-accepted',
    partial.locationSource === 'unknown' && partial.latitude == null,
    `(got locationSource=${partial.locationSource}, lat=${partial.latitude})`
  );

  // Malformed GPS (non-numeric, non-array garbage).
  const malformed = await resolvePhotoProvenance(
    libraryPick({ GPSLatitude: 'garbage', GPSLongitude: {}, GPSLatitudeRef: 'N', GPSLongitudeRef: 'E' })
  );
  check(
    'malformed GPS tags are rejected, not crashed on',
    malformed.locationSource === 'unknown' && malformed.latitude == null,
    `(got locationSource=${malformed.locationSource})`
  );

  // [deg, min, sec] triple format (raw EXIF wire format some Android readers pass through).
  const dms = await resolvePhotoProvenance(
    libraryPick({
      GPSLatitude: [17, 27, 7.344], GPSLatitudeRef: 'N',
      GPSLongitude: [78, 23, 59.2296], GPSLongitudeRef: 'E',
    })
  );
  check(
    'DMS-triple GPS format is parsed correctly',
    dms.locationSource === 'photo_exif'
      && Math.abs((dms.latitude ?? 0) - 17.45204) < 0.0001
      && Math.abs((dms.longitude ?? 0) - 78.399786) < 0.0001,
    `(got lat=${dms.latitude}, lon=${dms.longitude})`
  );

  // Southern/Western hemisphere refs must negate correctly.
  const hemisphere = await resolvePhotoProvenance(
    libraryPick({ GPSLatitude: 17.45204, GPSLatitudeRef: 'S', GPSLongitude: 78.399786, GPSLongitudeRef: 'W' })
  );
  check(
    'S/W hemisphere refs negate correctly',
    hemisphere.latitude === -17.45204 && hemisphere.longitude === -78.399786,
    `(got lat=${hemisphere.latitude}, lon=${hemisphere.longitude})`
  );

  // Invalid hemisphere ref (garbage) defaults to positive (documented existing behavior) --
  // still a real, in-range coordinate, not a crash.
  const badRef = await resolvePhotoProvenance(
    libraryPick({ GPSLatitude: 17.45204, GPSLatitudeRef: 'X', GPSLongitude: 78.399786, GPSLongitudeRef: 'Q' })
  );
  check('an unrecognized hemisphere ref does not crash', badRef.locationSource === 'photo_exif');

  console.log();
  if (failures > 0) {
    console.log(`FAILURES: ${failures}`);
    process.exit(1);
  }
  console.log('ALL PASSED');
}

run();
