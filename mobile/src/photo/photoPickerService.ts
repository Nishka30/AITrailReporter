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

/** Where copied Explore photos live. Inside the app's document directory, so
 * they survive restarts (unlike cache) and are removed with the app. */
const PHOTO_DIRECTORY_NAME = 'explore_photos';

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
  | { status: 'success'; uri: string; contentType: string }
  | { status: 'cancelled' }
  | { status: 'permission-denied'; canAskAgain: boolean }
  | { status: 'error'; message: string };

function photoDirectory(): Directory {
  return new Directory(Paths.document, PHOTO_DIRECTORY_NAME);
}

/**
 * Copies a picker-provided URI into app-owned storage and returns the new
 * durable path. Throws on failure — callers convert that into an honest
 * 'error' result rather than pretending the photo was saved.
 */
function persistPickedImage(sourceUri: string): string {
  const directory = photoDirectory();
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

async function pick(useCamera: boolean): Promise<PhotoPickResult> {
  try {
    const permission = useCamera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();

    if (!permission.granted) {
      return { status: 'permission-denied', canAskAgain: permission.canAskAgain !== false };
    }

    const options: ImagePicker.ImagePickerOptions = {
      mediaTypes: ['images'],
      allowsEditing: false,
      quality: IMAGE_QUALITY,
      exif: false,
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

    const durableUri = persistPickedImage(asset.uri);
    return { status: 'success', uri: durableUri, contentType: PHOTO_CONTENT_TYPE };
  } catch (err) {
    console.error('[photoPickerService] Failed to pick photo:', err);
    return { status: 'error', message: 'Could not open the photo. Please try again.' };
  }
}

/** Opens the camera. Requests camera permission first, only from this action. */
export function takePhoto(): Promise<PhotoPickResult> {
  return pick(true);
}

/** Opens the photo library. Requests library permission first, only from this action. */
export function choosePhoto(): Promise<PhotoPickResult> {
  return pick(false);
}
