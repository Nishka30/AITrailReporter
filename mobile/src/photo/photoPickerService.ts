import * as ImagePicker from 'expo-image-picker';
import { Directory, File, Paths } from 'expo-file-system';

/**
 * Photo capture for Explore contributions (Step 16).
 *
 * Follows exactly the same principles as the existing microphone and location
 * work (src/audio/audioRecordingService.ts, src/location/locationService.ts):
 *   - permission is requested ONLY from an explicit user action, never on mount
 *   - a denial is reported honestly and distinctly from an error
 *   - a cancellation is its own outcome, not a failure
 *   - nothing is ever fabricated on failure
 *
 * The picked image is COPIED into this app's own document directory before
 * being returned. That matters: the OS-provided picker URI points at a cache
 * or gallery location that can be reclaimed at any time, which is precisely
 * the class of bug that made voice notes silently unsendable earlier in this
 * project (see src/api/audio.ts's header). Copying means the file is still
 * there when sync eventually runs, possibly days later and after an app
 * restart.
 */

/** Where copied photos live. Inside the app's document directory, so they
 * survive restarts (unlike cache) and are removed with the app.
 *
 * Explore photos and profile photos are kept in SEPARATE directories (Step 17)
 * rather than one shared folder. They have genuinely different lifecycles: an
 * Explore photo belongs to one contribution and is retained because that
 * contribution may still need to sync, whereas a profile photo is a single
 * current value that is replaced outright when the guide picks a new one.
 * Mixing them would make "which files are still needed?" ambiguous.
 */
export type PhotoKind = 'explore' | 'profile';

const PHOTO_DIRECTORY_NAMES: Record<PhotoKind, string> = {
  explore: 'explore_photos',
  profile: 'profile_photos',
};

/** Matches the backend's ALLOWED_PHOTO_CONTENT_TYPES (see
 * backend/app/services/photo_validation.py). We request JPEG explicitly from
 * the picker below so this is the type we actually produce. */
export const PHOTO_CONTENT_TYPE = 'image/jpeg';

/** Downscale + recompress before upload. A modern phone photo can be 5-12 MB,
 * which is slow and expensive over a trail connection and far more resolution
 * than a condition report needs. 0.6 quality with the picker's own resizing
 * keeps files comfortably inside the backend's 10 MiB cap (see
 * max_photo_upload_size_bytes) while staying clearly readable. */
const IMAGE_QUALITY = 0.6;

export type PhotoPickResult =
  | {
      status: 'success';
      uri: string;
      contentType: string;
      /** Raw EXIF tags from the picker, or null if none were readable.
       * Interpretation (GPS decoding, capture time) is deliberately NOT done
       * here — see src/location/photoLocationResolver.ts, which is the only
       * place that turns these raw tags into location/date provenance. This
       * keeps "how do we pick a photo" and "what does this photo's metadata
       * mean" as separate concerns.
       *
       * KNOWN PLATFORM GAP: per Expo's own docs, iOS never includes GPS tags
       * in EXIF for a photo taken with the in-app camera (library picks and
       * Android are unaffected) — this is exactly why a LIVE capture must
       * also fall back to device GPS rather than relying on EXIF alone (see
       * the resolver). */
      exif: Record<string, unknown> | null;
      /** Whether this came from the camera (a live, right-now capture) or
       * the library (possibly an old photo). The resolver needs this: a
       * live camera photo with no EXIF GPS should fall back to CURRENT
       * device GPS, while a library photo with no EXIF GPS must NOT — it
       * could be from anywhere, any time. */
      source: 'camera' | 'library';
    }
  | { status: 'cancelled' }
  | { status: 'permission-denied'; canAskAgain: boolean }
  | { status: 'error'; message: string };

function photoDirectory(kind: PhotoKind): Directory {
  return new Directory(Paths.document, PHOTO_DIRECTORY_NAMES[kind]);
}

/**
 * Copies a picker-provided URI into app-owned storage and returns the new
 * durable path. Throws on failure — callers convert that into an honest
 * 'error' result rather than pretending the photo was saved.
 */
function persistPickedImage(sourceUri: string, kind: PhotoKind): string {
  const directory = photoDirectory(kind);
  if (!directory.exists) {
    directory.create({ intermediates: true });
  }
  const source = new File(sourceUri);
  // Server-style naming on the client too: a generated name plus the real
  // extension, never the OS-supplied filename pasted into a path.
  const extension = sourceUri.split('.').pop()?.toLowerCase();
  const safeExtension = extension && /^[a-z0-9]{1,5}$/.test(extension) ? extension : 'jpg';
  const destination = new File(directory, `${Date.now()}_${Math.floor(Math.random() * 1e6)}.${safeExtension}`);
  source.copy(destination);
  return destination.uri;
}

async function pick(useCamera: boolean, kind: PhotoKind): Promise<PhotoPickResult> {
  try {
    const permission = useCamera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();

    if (!permission.granted) {
      return { status: 'permission-denied', canAskAgain: permission.canAskAgain !== false };
    }

    const options: ImagePicker.ImagePickerOptions = {
      mediaTypes: ['images'],
      // Profile pictures are cropped to a square by the OS picker, because they
      // are ALWAYS displayed in a circular frame — letting the guide choose the
      // crop is far better than silently centre-cropping whatever they picked.
      // Explore photos are never cropped: the whole scene is the evidence.
      allowsEditing: kind === 'profile',
      ...(kind === 'profile' ? { aspect: [1, 1] as [number, number] } : {}),
      quality: IMAGE_QUALITY,
      // Read, never rely on: absent on iOS camera captures by platform
      // design, and not guaranteed present anywhere else either. See
      // PhotoPickResult's `exif` field and photoLocationResolver.ts, which
      // treat every EXIF field as independently-possibly-missing.
      exif: true,
    };

    const result = useCamera
      ? await ImagePicker.launchCameraAsync(options)
      : await ImagePicker.launchImageLibraryAsync(options);

    if (result.canceled) {
      return { status: 'cancelled' };
    }

    const asset = result.assets?.[0];
    if (!asset?.uri) {
      // Defensive: a non-cancelled result should always carry an asset. Never
      // guessed around — reported as the genuine anomaly it would be.
      return { status: 'error', message: 'The photo could not be read. Please try again.' };
    }

    const durableUri = persistPickedImage(asset.uri, kind);
    return {
      status: 'success',
      uri: durableUri,
      contentType: PHOTO_CONTENT_TYPE,
      exif: (asset.exif as Record<string, unknown> | undefined) ?? null,
      source: useCamera ? 'camera' : 'library',
    };
  } catch (err) {
    console.error('[photoPickerService] Failed to pick photo:', err);
    return { status: 'error', message: 'Could not open the photo. Please try again.' };
  }
}

/** Opens the camera. Requests camera permission first, only from this action. */
export function takePhoto(kind: PhotoKind = 'explore'): Promise<PhotoPickResult> {
  return pick(true, kind);
}

/** Opens the photo library. Requests library permission first, only from this action. */
export function choosePhoto(kind: PhotoKind = 'explore'): Promise<PhotoPickResult> {
  return pick(false, kind);
}

/**
 * Best-effort deletion of a photo this app previously copied into its own
 * storage (Step 17: replacing or removing a profile picture).
 *
 * Only ever called for a URI the app itself produced via persistPickedImage —
 * never for a picker/gallery URI, which belongs to the OS and must not be
 * touched. Failure is logged and swallowed: an orphaned file wastes a little
 * space, whereas throwing here would fail a profile save that otherwise
 * succeeded, which is strictly worse for the guide.
 */
export function deleteStoredPhoto(uri: string): void {
  try {
    const file = new File(uri);
    if (file.exists) file.delete();
  } catch (err) {
    console.error('[photoPickerService] Failed to delete stored photo:', err);
  }
}
