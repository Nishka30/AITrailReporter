import { useState } from 'react';
import { Image, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import type { PlaceSearchResult } from '../api/placeSearch';
import type { RecordedAudio } from '../audio/audioRecordingService';
import ApproximateDateField, { type ApproximateDateValue } from '../components/ApproximateDateField';
import PlaceAutocomplete from '../components/PlaceAutocomplete';
import VoiceNoteComposer from '../components/VoiceNoteComposer';
import { AppHeader, Badge, Button, Card, Screen } from '../components/ui';
import { resolvePhotoProvenance } from '../location/photoLocationResolver';
import { choosePhoto, takePhoto, type PhotoPickResult } from '../photo/photoPickerService';
import { createMemoryCapture, type CaptureProvenanceInput } from '../repositories/captureRepository';
import { colors, radii, spacing, type } from '../theme/theme';
import type { LocalGuide } from '../types/models';

type Props = {
  guide: LocalGuide;
  onDone: () => void;
};

type AttachedPhoto = { uri: string; contentType: string };

const EMPTY_PROVENANCE: CaptureProvenanceInput = {
  locationSource: 'unknown',
  occurredAtPrecision: 'unknown',
  dateSource: 'unknown',
};

function SectionLabel({
  icon,
  title,
  hint,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  hint?: string;
}) {
  return (
    <View style={styles.sectionLabelRow}>
      <Ionicons name={icon} size={14} color={colors.inkFaint} />
      <Text style={styles.sectionLabelTitle}>{title}</Text>
      {hint ? (
        <Text style={styles.sectionLabelHint} numberOfLines={1}>
          {hint}
        </Text>
      ) : null}
    </View>
  );
}

/** Turns resolved provenance into the one honest line the guide sees — never
 * more certain than what was actually established. */
function describeLocation(provenance: CaptureProvenanceInput): { label: string; tone: 'success' | 'neutral' } {
  switch (provenance.locationSource) {
    case 'photo_exif':
      return { label: 'Location verified — from your photo', tone: 'success' };
    case 'gps_live':
      return { label: 'Location verified — your current position', tone: 'success' };
    case 'user_selected':
      return { label: provenance.locationLabel ?? 'Place selected', tone: 'neutral' };
    default:
      return { label: 'No location yet', tone: 'neutral' };
  }
}

/**
 * "Share a Memory" — a TrailMind Explore card for content that isn't tied to
 * a live moment or a verified place: an old photo, a story recalled later.
 * Same composer as ExploreContributeScreen (same picker, same recorder, same
 * offline-first save-then-sync contract) with two additions this kind of
 * contribution specifically needs: WHERE this happened (auto-detected from a
 * photo when possible, otherwise searchable) and roughly WHEN.
 *
 * THE GUIDING PRINCIPLE: capture first, TrailMind figures out the context,
 * and the guide is only asked for what genuinely couldn't be determined.
 * Attaching a photo with GPS or a recent camera shot needs no further input
 * at all — the location/date sections simply confirm what was already
 * established. Only an old, GPS-less library photo (or no photo at all)
 * prompts the guide to say where/when.
 */
export default function MemoryContributeScreen({ guide, onDone }: Props) {
  const db = useSQLiteContext();
  const [text, setText] = useState('');
  const [photo, setPhoto] = useState<AttachedPhoto | null>(null);
  const [voice, setVoice] = useState<RecordedAudio | null>(null);
  const [provenance, setProvenance] = useState<CaptureProvenanceInput>(EMPTY_PROVENANCE);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [photoNotice, setPhotoNotice] = useState<string | null>(null);
  const [pickingPhoto, setPickingPhoto] = useState(false);
  const [resolvingLocation, setResolvingLocation] = useState(false);

  async function applyPhotoResult(result: PhotoPickResult) {
    switch (result.status) {
      case 'success': {
        setPhoto({ uri: result.uri, contentType: result.contentType });
        setPhotoNotice(null);
        // Quietly figures out where/when from the photo itself — the guide
        // is never asked to type coordinates. See photoLocationResolver.ts
        // for the exact decision tree (EXIF GPS -> live GPS for a camera
        // shot -> honestly unknown for an old library pick).
        setResolvingLocation(true);
        try {
          const resolved = await resolvePhotoProvenance(result);
          setProvenance((prev) => ({ ...prev, ...resolved }));
        } finally {
          setResolvingLocation(false);
        }
        break;
      }
      case 'cancelled':
        break;
      case 'permission-denied':
        setPhotoNotice(
          result.canAskAgain
            ? 'Photo permission is needed for this. Please allow it and try again.'
            : 'Photo permission was denied. You can enable it for this app in your device settings.'
        );
        break;
      case 'error':
        setPhotoNotice(result.message);
        break;
    }
  }

  async function handlePickPhoto(useCamera: boolean) {
    if (pickingPhoto || saving) return;
    setPickingPhoto(true);
    setPhotoNotice(null);
    try {
      await applyPhotoResult(useCamera ? await takePhoto() : await choosePhoto());
    } finally {
      setPickingPhoto(false);
    }
  }

  function handleRemovePhoto() {
    setPhoto(null);
    // The photo was the only source of the auto-detected location/date —
    // removing it must not leave a now-unexplained "verified" claim behind.
    if (provenance.locationSource === 'photo_exif' || provenance.locationSource === 'gps_live') {
      setProvenance(EMPTY_PROVENANCE);
    }
  }

  function handleSelectPlace(place: PlaceSearchResult) {
    setProvenance((prev) => ({
      ...prev,
      latitude: place.latitude,
      longitude: place.longitude,
      locationSource: 'user_selected',
      locationLabel: place.label,
      locationAccuracyMeters: null,
      locationCapturedAt: null,
    }));
  }

  function handleDateChange(value: ApproximateDateValue) {
    setProvenance((prev) => ({
      ...prev,
      occurredAt: value.occurredAt,
      occurredAtPrecision: value.precision,
      // A guide who explicitly picks a date typed it in themselves, UNLESS
      // it was already established from the photo (exif/device) — only
      // overwrite dateSource when this is genuinely a manual entry.
      dateSource:
        prev.dateSource === 'exif' || prev.dateSource === 'device' ? prev.dateSource : 'user_entered',
    }));
  }

  async function handleSave() {
    if (saving) return;
    const trimmed = text.trim();
    if (!trimmed && !voice && !photo) {
      setError('Add a photo, a voice note, or a few words about this memory.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createMemoryCapture(db, guide.id, trimmed || null, {
        localPhotoUri: photo?.uri ?? null,
        photoContentType: photo?.contentType ?? null,
        localAudioUri: voice?.uri ?? null,
        audioDurationMillis: voice?.durationMillis ?? null,
        audioContentType: voice?.contentType ?? null,
        ...provenance,
      });
      setSaved(true);
    } catch (err) {
      console.error('[MemoryContributeScreen] Failed to save memory:', err);
      setError('Could not save this on your device. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  function describeSaved(): string {
    const parts = [
      text.trim() ? 'note' : null,
      voice ? 'voice note' : null,
      photo ? 'photo' : null,
    ].filter(Boolean) as string[];
    const list =
      parts.length === 1
        ? `Your ${parts[0]} is`
        : `Your ${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]} are`;
    return `${list} stored safely on this device. Everything is sent the next time you sync.`;
  }

  if (saved) {
    return (
      <Screen>
        <AppHeader title="Saved" onBack={onDone} />
        <Card variant="outline" style={styles.savedCard}>
          <View style={styles.savedIcon}>
            <Ionicons name="checkmark-circle" size={30} color={colors.ok} />
          </View>
          <Text style={styles.savedTitle}>Memory saved</Text>
          <Text style={styles.savedBody}>{describeSaved()}</Text>
          <Badge label="Waiting to send" tone="info" icon="cloud-upload-outline" />
          <View style={styles.savedButton}>
            <Button label="Back to Explore" onPress={onDone} />
          </View>
        </Card>
      </Screen>
    );
  }

  const locationSummary = describeLocation(provenance);
  const showPlaceSearch = provenance.locationSource === 'unknown' || provenance.locationSource === 'user_selected';

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen>
        <AppHeader title="Share a Memory" onBack={onDone} />

        <Card style={styles.promptCard}>
          <Text style={styles.promptBody}>
            Tell us about a place you visited — a photo, a voice story, or just a few words. It
            doesn't have to be from right now.
          </Text>
        </Card>

        <SectionLabel icon="create-outline" title="Your words" hint={voice ? 'Optional — your voice note covers this' : undefined} />
        <TextInput
          style={styles.textArea}
          placeholder="What do you remember about this place?"
          placeholderTextColor={colors.inkFaint}
          value={text}
          onChangeText={setText}
          multiline
          numberOfLines={6}
          editable={!saving}
        />

        <SectionLabel icon="mic-outline" title="Voice story" hint={voice ? 'Attached' : 'Optional'} />
        <View style={styles.voiceWrap}>
          <VoiceNoteComposer
            value={voice}
            onChange={setVoice}
            idleCopy="Tell us the story in your own words"
            disabled={saving}
          />
        </View>

        <SectionLabel icon="camera-outline" title="Photo" hint="Optional" />
        {photo ? (
          <View style={styles.photoWrap}>
            <Image source={{ uri: photo.uri }} style={styles.photoPreview} resizeMode="cover" />
            <Pressable
              onPress={handleRemovePhoto}
              accessibilityRole="button"
              accessibilityLabel="Remove photo"
              hitSlop={8}
              style={styles.photoRemove}
              disabled={saving}
            >
              <Ionicons name="close" size={17} color={colors.white} />
            </Pressable>
          </View>
        ) : (
          <View style={styles.photoActions}>
            <Pressable
              onPress={() => handlePickPhoto(true)}
              accessibilityRole="button"
              accessibilityLabel="Take photo"
              disabled={pickingPhoto || saving}
              style={({ pressed }) => [
                styles.photoAction,
                pressed && styles.photoActionPressed,
                (pickingPhoto || saving) && styles.photoActionDisabled,
              ]}
            >
              <Ionicons name="camera-outline" size={21} color={colors.marigoldDeep} />
              <Text style={styles.photoActionText}>Take photo</Text>
            </Pressable>
            <Pressable
              onPress={() => handlePickPhoto(false)}
              accessibilityRole="button"
              accessibilityLabel="Choose an existing photo"
              disabled={pickingPhoto || saving}
              style={({ pressed }) => [
                styles.photoAction,
                pressed && styles.photoActionPressed,
                (pickingPhoto || saving) && styles.photoActionDisabled,
              ]}
            >
              <Ionicons name="images-outline" size={21} color={colors.marigoldDeep} />
              <Text style={styles.photoActionText}>Choose from library</Text>
            </Pressable>
          </View>
        )}
        {photoNotice ? <Text style={styles.notice}>{photoNotice}</Text> : null}

        <SectionLabel icon="location-outline" title="Where" />
        <View style={styles.locationBlock}>
          <Badge
            label={resolvingLocation ? 'Figuring out where this was…' : locationSummary.label}
            tone={resolvingLocation ? 'neutral' : locationSummary.tone}
            icon={resolvingLocation ? undefined : 'location'}
          />
          {showPlaceSearch && !resolvingLocation ? (
            <View style={styles.placeSearchWrap}>
              <PlaceAutocomplete
                guideId={guide.serverGuideId ?? ''}
                onSelect={handleSelectPlace}
                placeholder="Search for the place this happened…"
                disabled={saving || !guide.serverGuideId}
              />
              {!guide.serverGuideId ? (
                <Text style={styles.notice}>
                  Place search needs your profile to sync at least once — you can still save this
                  memory without a place for now.
                </Text>
              ) : null}
            </View>
          ) : null}
        </View>

        <SectionLabel icon="calendar-outline" title="When" />
        <View style={styles.dateBlock}>
          <ApproximateDateField
            value={{ occurredAt: provenance.occurredAt ?? null, precision: provenance.occurredAtPrecision ?? 'unknown' }}
            onChange={handleDateChange}
            disabled={saving}
          />
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <View style={styles.saveButton}>
          <Button label={saving ? 'Saving…' : 'Save memory'} onPress={handleSave} loading={saving} />
        </View>

        <Text style={styles.footnote}>
          Saved on this device right away — no connection needed now. Everything is sent the next
          time you sync.
        </Text>
      </Screen>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  promptCard: { marginBottom: spacing.lg },
  promptBody: { ...type.subtitle, color: colors.ink, lineHeight: 24 },

  sectionLabelRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: spacing.xs },
  sectionLabelTitle: { ...type.captionBold, color: colors.inkFaint, letterSpacing: 0.5, textTransform: 'uppercase' },
  sectionLabelHint: { ...type.caption, color: colors.inkFaint, opacity: 0.75, flexShrink: 1, marginLeft: 'auto' },

  voiceWrap: { marginBottom: spacing.lg },
  textArea: {
    backgroundColor: colors.paperElevated,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    ...type.body,
    color: colors.ink,
    minHeight: 110,
    textAlignVertical: 'top',
    marginBottom: spacing.lg,
  },

  photoActions: { flexDirection: 'row', gap: spacing.sm },
  photoAction: {
    flex: 1,
    minHeight: 84,
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
  photoActionText: { ...type.smallBold, color: colors.marigoldDeep },

  photoWrap: { position: 'relative' },
  photoPreview: { width: '100%', height: 210, borderRadius: radii.md, backgroundColor: colors.paperMuted },
  photoRemove: {
    position: 'absolute',
    top: spacing.xs,
    right: spacing.xs,
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: 'rgba(33,26,20,0.75)',
    alignItems: 'center',
    justifyContent: 'center',
  },

  locationBlock: { marginTop: spacing.xs, marginBottom: spacing.lg, gap: spacing.sm },
  placeSearchWrap: { gap: spacing.xs },
  dateBlock: { marginTop: spacing.xs, marginBottom: spacing.lg },

  notice: { ...type.small, color: colors.inkSoft, marginTop: spacing.sm },
  error: { ...type.small, color: colors.fix, marginTop: spacing.sm },
  saveButton: { marginTop: spacing.md },
  footnote: { ...type.caption, color: colors.inkFaint, marginTop: spacing.md, lineHeight: 17, textAlign: 'center' },

  savedCard: { alignItems: 'center', gap: spacing.sm, marginTop: spacing.xl },
  savedIcon: { marginBottom: spacing.xxs },
  savedTitle: { ...type.title, color: colors.ink, textAlign: 'center' },
  savedBody: { ...type.body, color: colors.inkSoft, textAlign: 'center', lineHeight: 22 },
  savedButton: { alignSelf: 'stretch', marginTop: spacing.sm },
});
