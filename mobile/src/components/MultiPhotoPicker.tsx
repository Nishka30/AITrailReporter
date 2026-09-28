import { useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import {
  choosePhotos,
  takePhoto,
  type PhotoPickMultiResult,
  type PhotoPickResult,
} from '../photo/photoPickerService';
import { colors, radii, spacing, type } from '../theme/theme';

export type AttachedPhoto = {
  uri: string;
  contentType: string;
  /** The OS media library's id for this photo, when the picker provided one
   * -- carried along purely so a LATER gallery pick can detect "you already
   * added this one" (see applyMultiResult below). Never read by anything
   * downstream of this component (repositories only ever read uri/contentType
   * -- see e.g. MemoryContributeScreen's save handler). */
  assetId?: string | null;
};

/** Mirrors the backend's settings.max_photos_per_submission (see
 * backend/app/core/config.py) -- a soft, disclosed cap on how many photos ONE
 * contribution may carry. Enforced here too so a guide finds out before
 * saving, not as a sync failure afterward. */
export const MAX_PHOTOS_PER_CAPTURE = 6;

/**
 * Multi-image attach control shared by every composer that used to allow
 * exactly one photo (MemoryContributeScreen, ExploreContributeScreen,
 * AnswerQuestionScreen). Each screen owns the `photos` array as local state
 * and passes it down here alongside `onChange`; this component only ever
 * picks/removes, it never persists anything itself.
 *
 * Deliberately ONE shared component rather than three copies of the same
 * take/choose/preview/remove UI -- the three screens' single-photo blocks
 * were byte-for-byte identical before this, so tripling them for
 * multi-image would have been the wrong kind of "smallest change".
 */
export default function MultiPhotoPicker({
  photos,
  onChange,
  disabled = false,
  maxPhotos = MAX_PHOTOS_PER_CAPTURE,
  onPhotoPicked,
}: {
  photos: AttachedPhoto[];
  onChange: (photos: AttachedPhoto[]) => void;
  disabled?: boolean;
  maxPhotos?: number;
  /** Fired after a successful pick, in addition to onChange -- for a caller
   * that needs the raw picker result itself (MemoryContributeScreen uses
   * this to auto-detect location/date from the FIRST photo's EXIF data via
   * photoLocationResolver.ts; most callers don't need it at all).
   * `wasFirstPhoto` reflects the count BEFORE this pick was added. */
  onPhotoPicked?: (
    result: Extract<PhotoPickResult, { status: 'success' }>,
    wasFirstPhoto: boolean
  ) => void;
}) {
  const [picking, setPicking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const atCap = photos.length >= maxPhotos;

  function applyResult(result: PhotoPickResult) {
    switch (result.status) {
      case 'success': {
        const wasFirstPhoto = photos.length === 0;
        onChange([
          ...photos,
          { uri: result.uri, contentType: result.contentType, assetId: result.assetId ?? null },
        ]);
        onPhotoPicked?.(result, wasFirstPhoto);
        setNotice(null);
        break;
      }
      case 'cancelled':
        // Not an error, and not worth a message -- the guide chose to back out.
        break;
      case 'permission-denied':
        setNotice(
          result.canAskAgain
            ? 'Photo permission is needed for this. Please allow it and try again.'
            : 'Photo permission was denied. You can enable it for this app in your device settings.'
        );
        break;
      case 'error':
        setNotice(result.message);
        break;
    }
  }

  /** Handles a native MULTI-SELECT gallery result: dedupes against photos
   * already attached (and against duplicates within the same selection) by
   * the OS media library's asset id, then keeps only as many of the
   * remainder as there is room for. A photo whose id isn't available (see
   * PhotoPickResult.assetId's doc comment) is always treated as new, since
   * there is no reliable way to tell otherwise. */
  function applyMultiResult(result: PhotoPickMultiResult) {
    switch (result.status) {
      case 'success': {
        const wasEmpty = photos.length === 0;
        const alreadyAttached = new Set(
          photos.map((p) => p.assetId).filter((id): id is string => !!id)
        );
        const remaining = maxPhotos - photos.length;
        const seenInThisBatch = new Set<string>();
        const accepted: typeof result.photos = [];
        for (const picked of result.photos) {
          if (accepted.length >= remaining) break;
          if (picked.assetId) {
            if (alreadyAttached.has(picked.assetId) || seenInThisBatch.has(picked.assetId)) {
              continue;
            }
            seenInThisBatch.add(picked.assetId);
          }
          accepted.push(picked);
        }

        if (accepted.length > 0) {
          onChange([
            ...photos,
            ...accepted.map((p) => ({
              uri: p.uri,
              contentType: p.contentType,
              assetId: p.assetId ?? null,
            })),
          ]);
          if (wasEmpty) {
            // Same "auto-detect from the first photo" hook single-pick fires
            // -- fired once, for the first newly-added photo, exactly like a
            // single camera/library pick into an empty list.
            const first = accepted[0];
            onPhotoPicked?.(
              {
                status: 'success',
                uri: first.uri,
                contentType: first.contentType,
                exif: first.exif,
                source: 'library',
                assetId: first.assetId ?? null,
              },
              true
            );
          }
        }
        setNotice(null);
        break;
      }
      case 'cancelled':
        break;
      case 'permission-denied':
        setNotice(
          result.canAskAgain
            ? 'Photo permission is needed for this. Please allow it and try again.'
            : 'Photo permission was denied. You can enable it for this app in your device settings.'
        );
        break;
      case 'error':
        setNotice(result.message);
        break;
    }
  }

  async function handleTakePhoto() {
    if (picking || disabled || atCap) return;
    setPicking(true);
    setNotice(null);
    try {
      applyResult(await takePhoto());
    } finally {
      setPicking(false);
    }
  }

  async function handlePickFromLibrary() {
    if (picking || disabled || atCap) return;
    setPicking(true);
    setNotice(null);
    try {
      applyMultiResult(await choosePhotos('explore', maxPhotos - photos.length));
    } finally {
      setPicking(false);
    }
  }

  function handleRemove(index: number) {
    onChange(photos.filter((_, i) => i !== index));
  }

  return (
    <View>
      {photos.length > 0 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.thumbRow}>
          {photos.map((photo, index) => (
            <View key={`${photo.uri}-${index}`} style={styles.thumbWrap}>
              <Image source={{ uri: photo.uri }} style={styles.thumb} resizeMode="cover" />
              <Pressable
                onPress={() => handleRemove(index)}
                accessibilityRole="button"
                accessibilityLabel={`Remove photo ${index + 1}`}
                hitSlop={8}
                style={styles.thumbRemove}
                disabled={disabled}
              >
                <Ionicons name="close" size={15} color={colors.white} />
              </Pressable>
            </View>
          ))}
        </ScrollView>
      ) : null}

      {atCap ? (
        <Text style={styles.notice}>Maximum {maxPhotos} photos per contribution.</Text>
      ) : (
        <View style={styles.photoActions}>
          <Pressable
            onPress={handleTakePhoto}
            accessibilityRole="button"
            accessibilityLabel="Take photo"
            disabled={picking || disabled}
            style={({ pressed }) => [
              styles.photoAction,
              pressed && styles.photoActionPressed,
              (picking || disabled) && styles.photoActionDisabled,
            ]}
          >
            <Ionicons name="camera-outline" size={21} color={colors.marigoldDeep} />
            <Text style={styles.photoActionText}>
              {photos.length === 0 ? 'Take photo' : 'Add another'}
            </Text>
          </Pressable>
          <Pressable
            onPress={handlePickFromLibrary}
            accessibilityRole="button"
            accessibilityLabel="Choose from library"
            disabled={picking || disabled}
            style={({ pressed }) => [
              styles.photoAction,
              pressed && styles.photoActionPressed,
              (picking || disabled) && styles.photoActionDisabled,
            ]}
          >
            <Ionicons name="images-outline" size={21} color={colors.marigoldDeep} />
            <Text style={styles.photoActionText}>
              {photos.length === 0 ? 'Choose from library' : 'Add from library'}
            </Text>
          </Pressable>
        </View>
      )}
      {notice ? <Text style={styles.notice}>{notice}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  thumbRow: { marginBottom: spacing.sm },
  thumbWrap: { position: 'relative', marginRight: spacing.sm },
  thumb: { width: 92, height: 92, borderRadius: radii.md, backgroundColor: colors.paperMuted },
  thumbRemove: {
    position: 'absolute',
    top: 4,
    right: 4,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: 'rgba(33,26,20,0.75)',
    alignItems: 'center',
    justifyContent: 'center',
  },

  // flexBasis: 0 (rather than the 'auto' that a bare `flex: 1` leaves as the
  // starting point) is what actually guarantees the two actions divide the
  // row exactly in half regardless of their label length -- "Add another"
  // and "Add from library" are different lengths, and without an explicit
  // basis their intrinsic content size can nudge the split off-center.
  photoActions: { flexDirection: 'row', gap: spacing.sm },
  photoAction: {
    flex: 1,
    flexBasis: 0,
    minHeight: 72,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderStyle: 'dashed',
    backgroundColor: colors.paperMuted,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  photoActionPressed: { opacity: 0.8 },
  photoActionDisabled: { opacity: 0.5 },
  // centered explicitly: without it, a label that wraps to a second line
  // (e.g. "Add from" / "library") left-aligns its shorter second line rather
  // than centering under the first, which is what read as the button's text
  // -- and by extension the button itself -- looking shifted left.
  photoActionText: { ...type.smallBold, color: colors.marigoldDeep, textAlign: 'center' },

  notice: { ...type.small, color: colors.inkSoft, marginTop: spacing.sm },
});
