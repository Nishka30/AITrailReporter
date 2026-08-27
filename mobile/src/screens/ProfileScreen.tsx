import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { AppHeader, Avatar, Badge, Button, Card, Screen } from '../components/ui';
import {
  choosePhoto,
  deleteStoredPhoto,
  takePhoto,
  type PhotoPickResult,
} from '../photo/photoPickerService';
import { normalizePhoneNumber, validatePhoneNumber } from '../profile/phone';
import { updateLocalGuideProfile } from '../repositories/guideRepository';
import { colors, minTouchSize, radii, spacing, type } from '../theme/theme';
import type { LocalGuide } from '../types/models';

type Props = {
  guide: LocalGuide;
  /** Called after a successful save (and on plain back), so the navigator can
   * re-read the guide and every screen sees the new name/photo. */
  onDone: () => void;
};

/** Soft cap on the About text. Not a backend constraint — this field never
 * leaves the device — purely a product judgement that a field profile is a
 * short introduction, not an essay, plus it keeps the row small. */
const ABOUT_MAX_LENGTH = 400;

/**
 * The guide's profile (Step 17), opened by tapping their avatar in the Home
 * header.
 *
 * IDENTITY MODEL: this edits the EXISTING local_guide row — the app's single
 * identity. There is deliberately no separate "user" or "profile" entity: the
 * guide already had name, phone_number and a stable client_guide_id, is what
 * every capture/location/answer is attributed to, and is what the backend knows
 * about. Adding a parallel model would have meant two sources of truth for the
 * same person and a merge problem at every sync.
 *
 * WHAT SYNCS, AND WHAT DOESN'T:
 *   - name, phone_number  -> pushed to the backend Guide (it already has these
 *                            columns) via the sync engine's normal outbox.
 *   - about, photo        -> LOCAL TO THIS DEVICE, always. They are personal
 *                            metadata, not field knowledge: never uploaded,
 *                            never turned into Observations, never included in
 *                            any transcription or LLM request.
 *
 * Fully offline: saving writes to SQLite and returns. A server push, if one is
 * needed, happens later during a normal sync — never blocking this screen.
 */
export default function ProfileScreen({ guide, onDone }: Props) {
  const db = useSQLiteContext();

  const [name, setName] = useState(guide.name);
  const [phone, setPhone] = useState(guide.phoneNumber ?? '');
  const [about, setAbout] = useState(guide.aboutText ?? '');
  const [photoUri, setPhotoUri] = useState<string | null>(guide.localPhotoUri);

  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [photoNotice, setPhotoNotice] = useState<string | null>(null);
  const [pickingPhoto, setPickingPhoto] = useState(false);

  // Tracks photos this screen wrote to disk but has not yet committed to
  // SQLite. If the guide picks three pictures and saves once, the two
  // superseded files must not be left behind — but they also must not be
  // deleted eagerly, because until Save is pressed the STORED photo is still
  // the one the profile legitimately uses.
  const [uncommittedPhotos, setUncommittedPhotos] = useState<string[]>([]);

  const existingPhoneMissing = !guide.phoneNumber;

  function applyPhotoResult(result: PhotoPickResult) {
    switch (result.status) {
      case 'success':
        setUncommittedPhotos((prev) => [...prev, result.uri]);
        setPhotoUri(result.uri);
        setPhotoNotice(null);
        setSavedMessage(null);
        break;
      case 'cancelled':
        break;
      case 'permission-denied':
        setPhotoNotice(
          result.canAskAgain
            ? 'Photo access is needed for this. Please allow it and try again.'
            : 'Photo access was denied. You can enable it for this app in your device settings.'
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
      applyPhotoResult(useCamera ? await takePhoto('profile') : await choosePhoto('profile'));
    } finally {
      setPickingPhoto(false);
    }
  }

  function handleRemovePhoto() {
    if (saving) return;
    setPhotoUri(null);
    setPhotoNotice(null);
    setSavedMessage(null);
  }

  async function handleSave() {
    if (saving) return;

    const trimmedName = name.trim();
    if (!trimmedName) {
      setError('Please enter your name.');
      return;
    }

    const phoneCheck = validatePhoneNumber(phone);
    if (!phoneCheck.valid) {
      setError(phoneCheck.message);
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const trimmedAbout = about.trim();
      await updateLocalGuideProfile(db, guide.id, {
        name: trimmedName,
        phoneNumber: normalizePhoneNumber(phone),
        aboutText: trimmedAbout ? trimmedAbout : null,
        localPhotoUri: photoUri,
      });

      // Only now that SQLite has committed is it safe to delete the files this
      // session created but did not end up using — including a previously
      // stored photo that has just been replaced or removed. Doing this before
      // the write would risk deleting a photo the saved profile still points at.
      const survivors = new Set(photoUri ? [photoUri] : []);
      const obsolete = [...uncommittedPhotos, guide.localPhotoUri].filter(
        (uri): uri is string => Boolean(uri) && !survivors.has(uri as string)
      );
      obsolete.forEach(deleteStoredPhoto);
      setUncommittedPhotos([]);

      setSavedMessage('Profile saved on this device.');
      onDone();
    } catch (err) {
      console.error('[ProfileScreen] Failed to save profile:', err);
      setError('Could not save your profile on this device. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  const aboutRemaining = ABOUT_MAX_LENGTH - about.length;

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <Screen>
        <AppHeader title="Profile" onBack={onDone} />

        {/* Identity header: the avatar is both the preview and the control. */}
        <View style={styles.avatarBlock}>
          <Pressable
            onPress={() => handlePickPhoto(false)}
            disabled={pickingPhoto || saving}
            accessibilityRole="button"
            accessibilityLabel={photoUri ? 'Change profile photo' : 'Add a profile photo'}
            style={({ pressed }) => [styles.avatarPressable, pressed && styles.pressed]}
          >
            <Avatar name={name} photoUri={photoUri} size={104} />
            <View style={styles.avatarEditBadge}>
              <Ionicons name="camera" size={15} color={colors.white} />
            </View>
          </Pressable>

          <View style={styles.photoActionsRow}>
            <Pressable
              onPress={() => handlePickPhoto(true)}
              disabled={pickingPhoto || saving}
              accessibilityRole="button"
              accessibilityLabel="Take a profile photo"
              style={({ pressed }) => [styles.photoChip, pressed && styles.pressed]}
            >
              <Ionicons name="camera-outline" size={15} color={colors.marigoldDeep} />
              <Text style={styles.photoChipText}>Camera</Text>
            </Pressable>
            <Pressable
              onPress={() => handlePickPhoto(false)}
              disabled={pickingPhoto || saving}
              accessibilityRole="button"
              accessibilityLabel="Choose a profile photo"
              style={({ pressed }) => [styles.photoChip, pressed && styles.pressed]}
            >
              <Ionicons name="images-outline" size={15} color={colors.marigoldDeep} />
              <Text style={styles.photoChipText}>Gallery</Text>
            </Pressable>
            {photoUri ? (
              <Pressable
                onPress={handleRemovePhoto}
                disabled={saving}
                accessibilityRole="button"
                accessibilityLabel="Remove profile photo"
                style={({ pressed }) => [styles.photoChipDanger, pressed && styles.pressed]}
              >
                <Ionicons name="trash-outline" size={15} color={colors.fix} />
                <Text style={styles.photoChipDangerText}>Remove</Text>
              </Pressable>
            ) : null}
          </View>

          {photoNotice ? <Text style={styles.notice}>{photoNotice}</Text> : null}
        </View>

        {/* Prompt rather than block: an existing guide from before Step 17 has
            no phone number, and their profile is not "invalid" — it is simply
            incomplete, and they are asked to finish it, not locked out. */}
        {existingPhoneMissing ? (
          <Card variant="flat" style={styles.completeCard}>
            <View style={styles.completeRow}>
              <Ionicons name="information-circle-outline" size={17} color={colors.info} />
              <Text style={styles.completeText}>
                Add your phone number to complete your profile. Everything you have already saved is
                untouched.
              </Text>
            </View>
          </Card>
        ) : null}

        <Text style={styles.fieldLabel}>Your name</Text>
        <TextInput
          style={styles.input}
          placeholder="Your name"
          placeholderTextColor={colors.inkFaint}
          value={name}
          onChangeText={(v) => {
            setName(v);
            setSavedMessage(null);
          }}
          editable={!saving}
          autoCapitalize="words"
        />

        <Text style={styles.fieldLabel}>Phone number</Text>
        <TextInput
          style={styles.input}
          placeholder="e.g. +91 98765 43210"
          placeholderTextColor={colors.inkFaint}
          value={phone}
          onChangeText={(v) => {
            setPhone(v);
            setSavedMessage(null);
          }}
          editable={!saving}
          keyboardType="phone-pad"
          maxLength={32}
        />
        <Text style={styles.fieldHint}>
          Shared with the Trail Reporter team so they can reach you about your reports.
        </Text>

        <View style={styles.aboutLabelRow}>
          <Text style={styles.fieldLabel}>About you</Text>
          <Text style={styles.optionalTag}>Optional</Text>
        </View>
        <TextInput
          style={styles.aboutArea}
          placeholder="Your interests, the routes you know best, or anything you'd like to share…"
          placeholderTextColor={colors.inkFaint}
          value={about}
          onChangeText={(v) => {
            setAbout(v);
            setSavedMessage(null);
          }}
          multiline
          numberOfLines={5}
          editable={!saving}
          maxLength={ABOUT_MAX_LENGTH}
        />
        <View style={styles.aboutFooterRow}>
          <Text style={styles.fieldHint}>Stays on this device — never uploaded.</Text>
          <Text style={[styles.counter, aboutRemaining < 40 && styles.counterLow]}>
            {aboutRemaining}
          </Text>
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}
        {savedMessage ? (
          <View style={styles.savedRow}>
            <Badge label={savedMessage} tone="success" icon="checkmark-circle-outline" />
          </View>
        ) : null}

        <View style={styles.saveWrap}>
          <Button
            label={saving ? 'Saving…' : 'Save profile'}
            onPress={handleSave}
            loading={saving}
          />
        </View>

        {/* States the privacy boundary plainly, in the place it applies. */}
        <Card variant="flat" style={styles.privacyCard}>
          <View style={styles.privacyRow}>
            <Ionicons name="lock-closed-outline" size={15} color={colors.inkFaint} />
            <Text style={styles.privacyText}>
              Your photo and "About you" note never leave this device. Your name and phone number
              are sent with your reports so the team knows who filed them. None of this is treated
              as trail knowledge.
            </Text>
          </View>
        </Card>
      </Screen>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  pressed: { opacity: 0.75 },

  avatarBlock: { alignItems: 'center', marginBottom: spacing.lg },
  avatarPressable: { position: 'relative' },
  avatarEditBadge: {
    position: 'absolute',
    right: -2,
    bottom: -2,
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.marigoldDeep,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: colors.paper,
  },
  photoActionsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: spacing.xs,
    marginTop: spacing.md,
  },
  photoChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    minHeight: 38,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.pill,
    backgroundColor: colors.marigoldSoft,
  },
  photoChipText: { ...type.smallBold, color: colors.marigoldDeep },
  photoChipDanger: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    minHeight: 38,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.pill,
    backgroundColor: colors.fixSoft,
  },
  photoChipDangerText: { ...type.smallBold, color: colors.fix },

  completeCard: { marginBottom: spacing.md, backgroundColor: colors.infoSoft },
  completeRow: { flexDirection: 'row', gap: spacing.xs, alignItems: 'flex-start' },
  completeText: { ...type.small, color: colors.inkSoft, flex: 1, lineHeight: 18 },

  fieldLabel: {
    ...type.captionBold,
    color: colors.inkFaint,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginBottom: spacing.xs,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.paperElevated,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    minHeight: minTouchSize,
    paddingVertical: spacing.sm,
    ...type.body,
    color: colors.ink,
  },
  fieldHint: { ...type.caption, color: colors.inkFaint, marginTop: 5, marginBottom: spacing.md },

  aboutLabelRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  optionalTag: {
    ...type.caption,
    color: colors.inkFaint,
    opacity: 0.8,
    marginBottom: spacing.xs,
  },
  aboutArea: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.paperElevated,
    borderRadius: radii.md,
    padding: spacing.md,
    ...type.body,
    color: colors.ink,
    minHeight: 118,
    textAlignVertical: 'top',
  },
  aboutFooterRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  counter: { ...type.caption, color: colors.inkFaint, marginTop: 5 },
  counterLow: { color: colors.marigoldDeep },

  error: { ...type.small, color: colors.fix, marginBottom: spacing.xs },
  notice: { ...type.small, color: colors.inkSoft, marginTop: spacing.xs, textAlign: 'center' },
  savedRow: { flexDirection: 'row', marginBottom: spacing.xs },
  saveWrap: { marginTop: spacing.xs },

  privacyCard: { marginTop: spacing.md },
  privacyRow: { flexDirection: 'row', gap: spacing.xs, alignItems: 'flex-start' },
  privacyText: { ...type.caption, color: colors.inkFaint, flex: 1, lineHeight: 17 },
});
