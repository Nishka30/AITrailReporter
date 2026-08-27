import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { Avatar, Button } from '../components/ui';
import {
  choosePhoto,
  deleteStoredPhoto,
  takePhoto,
  type PhotoPickResult,
} from '../photo/photoPickerService';
import { normalizePhoneNumber, validatePhoneNumber } from '../profile/phone';
import { createLocalGuide } from '../repositories/guideRepository';
import { colors, minTouchSize, radii, spacing, type } from '../theme/theme';

type Props = {
  onGuideCreated: () => void;
};

const ABOUT_MAX_LENGTH = 400;

/**
 * First-run setup (Step 17: now collects the full field profile).
 *
 * Name and phone number are REQUIRED — they are the identity every report is
 * attributed to, and both already exist on the backend Guide. The photo and the
 * "About you" note are genuinely optional and can be added later from the
 * Profile screen, so onboarding stays short: two fields to fill, everything
 * else skippable at a glance.
 *
 * Entirely offline, like every other write in this app: it creates the local
 * guide row and returns. The backend guide is created later, by the sync
 * engine, from these same values.
 */
export default function SetupScreen({ onGuideCreated }: Props) {
  const db = useSQLiteContext();
  const insets = useSafeAreaInsets();

  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [about, setAbout] = useState('');
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [showAbout, setShowAbout] = useState(false);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [photoNotice, setPhotoNotice] = useState<string | null>(null);
  const [pickingPhoto, setPickingPhoto] = useState(false);

  function applyPhotoResult(result: PhotoPickResult) {
    switch (result.status) {
      case 'success':
        // Nothing is committed yet, so a superseded pick can be deleted at once.
        if (photoUri) deleteStoredPhoto(photoUri);
        setPhotoUri(result.uri);
        setPhotoNotice(null);
        break;
      case 'cancelled':
        break;
      case 'permission-denied':
        setPhotoNotice(
          result.canAskAgain
            ? 'Photo access is needed for this. Please allow it and try again.'
            : 'Photo access was denied. You can add a photo later from your profile.'
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
      await createLocalGuide(db, trimmedName, normalizePhoneNumber(phone), {
        aboutText: trimmedAbout ? trimmedAbout : null,
        localPhotoUri: photoUri,
      });
      onGuideCreated();
    } catch (err) {
      console.error('[SetupScreen] Failed to save local guide profile:', err);
      setError('Could not save your profile on this device. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        style={styles.flex}
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + spacing.xl, paddingBottom: spacing.xxl },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.iconCircle}>
          <Ionicons name="trail-sign-outline" size={28} color={colors.marigoldDeep} />
        </View>

        <Text style={styles.title}>Welcome</Text>
        <Text style={styles.subtitle}>
          Let's set up your field profile. It's saved on this device — no connection needed.
        </Text>

        {/* Optional, and presented as such: a tappable avatar rather than a
            required upload step standing between the guide and the app. */}
        <View style={styles.avatarBlock}>
          <Pressable
            onPress={() => handlePickPhoto(false)}
            disabled={pickingPhoto || saving}
            accessibilityRole="button"
            accessibilityLabel={photoUri ? 'Change profile photo' : 'Add a profile photo'}
            style={({ pressed }) => [styles.avatarPressable, pressed && styles.pressed]}
          >
            <Avatar name={name || '?'} photoUri={photoUri} size={92} />
            <View style={styles.avatarEditBadge}>
              <Ionicons name={photoUri ? 'camera' : 'add'} size={16} color={colors.white} />
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
              <Ionicons name="camera-outline" size={14} color={colors.marigoldDeep} />
              <Text style={styles.photoChipText}>Camera</Text>
            </Pressable>
            <Pressable
              onPress={() => handlePickPhoto(false)}
              disabled={pickingPhoto || saving}
              accessibilityRole="button"
              accessibilityLabel="Choose a profile photo"
              style={({ pressed }) => [styles.photoChip, pressed && styles.pressed]}
            >
              <Ionicons name="images-outline" size={14} color={colors.marigoldDeep} />
              <Text style={styles.photoChipText}>Gallery</Text>
            </Pressable>
          </View>
          <Text style={styles.photoOptional}>Photo is optional</Text>
          {photoNotice ? <Text style={styles.notice}>{photoNotice}</Text> : null}
        </View>

        <Text style={styles.fieldLabel}>Your name</Text>
        <TextInput
          style={styles.input}
          placeholder="Your name"
          placeholderTextColor={colors.inkFaint}
          value={name}
          onChangeText={setName}
          autoFocus
          autoCapitalize="words"
          editable={!saving}
        />

        <Text style={[styles.fieldLabel, styles.fieldLabelSpaced]}>Phone number</Text>
        <TextInput
          style={styles.input}
          placeholder="e.g. +91 98765 43210"
          placeholderTextColor={colors.inkFaint}
          value={phone}
          onChangeText={setPhone}
          keyboardType="phone-pad"
          maxLength={32}
          editable={!saving}
        />
        <Text style={styles.fieldHint}>So the team can reach you about your reports.</Text>

        {/* Collapsed by default — deliberately one tap away rather than a third
            field to scroll past. It can equally be filled in later. */}
        {showAbout ? (
          <>
            <View style={styles.aboutLabelRow}>
              <Text style={styles.fieldLabel}>About you</Text>
              <Text style={styles.optionalTag}>Optional</Text>
            </View>
            <TextInput
              style={styles.aboutArea}
              placeholder="Your interests, the routes you know best, or anything you'd like to share…"
              placeholderTextColor={colors.inkFaint}
              value={about}
              onChangeText={setAbout}
              multiline
              numberOfLines={4}
              maxLength={ABOUT_MAX_LENGTH}
              editable={!saving}
            />
            <Text style={styles.fieldHint}>Stays on this device — never uploaded.</Text>
          </>
        ) : (
          <Pressable
            onPress={() => setShowAbout(true)}
            accessibilityRole="button"
            accessibilityLabel="Add something about yourself"
            style={({ pressed }) => [styles.addAboutRow, pressed && styles.pressed]}
          >
            <Ionicons name="add-circle-outline" size={17} color={colors.marigoldDeep} />
            <Text style={styles.addAboutText}>Tell us about yourself (optional)</Text>
          </Pressable>
        )}

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <View style={styles.saveWrap}>
          <Button
            label={saving ? 'Saving…' : 'Save and continue'}
            onPress={handleSave}
            loading={saving}
          />
        </View>

        <Text style={styles.footnote}>You can change any of this later from your profile.</Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.paper },
  content: { paddingHorizontal: spacing.xl },
  pressed: { opacity: 0.75 },

  iconCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.marigoldSoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  title: { ...type.display, color: colors.ink, marginBottom: spacing.xxs },
  subtitle: { ...type.body, color: colors.inkSoft, marginBottom: spacing.lg, lineHeight: 22 },

  avatarBlock: { alignItems: 'center', marginBottom: spacing.lg },
  avatarPressable: { position: 'relative' },
  avatarEditBadge: {
    position: 'absolute',
    right: -2,
    bottom: -2,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.marigoldDeep,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: colors.paper,
  },
  photoActionsRow: { flexDirection: 'row', gap: spacing.xs, marginTop: spacing.sm },
  photoChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    minHeight: 36,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.pill,
    backgroundColor: colors.marigoldSoft,
  },
  photoChipText: { ...type.smallBold, color: colors.marigoldDeep },
  photoOptional: { ...type.caption, color: colors.inkFaint, marginTop: 6 },

  fieldLabel: {
    ...type.captionBold,
    color: colors.inkFaint,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginBottom: spacing.xs,
  },
  fieldLabelSpaced: { marginTop: spacing.xs },
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
  optionalTag: { ...type.caption, color: colors.inkFaint, opacity: 0.8, marginBottom: spacing.xs },
  aboutArea: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.paperElevated,
    borderRadius: radii.md,
    padding: spacing.md,
    ...type.body,
    color: colors.ink,
    minHeight: 100,
    textAlignVertical: 'top',
  },
  addAboutRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    minHeight: minTouchSize,
    marginBottom: spacing.xs,
  },
  addAboutText: { ...type.smallBold, color: colors.marigoldDeep },

  error: { ...type.small, color: colors.fix, marginBottom: spacing.sm },
  notice: { ...type.small, color: colors.inkSoft, marginTop: spacing.xs, textAlign: 'center' },
  saveWrap: { marginTop: spacing.xs },
  footnote: {
    ...type.caption,
    color: colors.inkFaint,
    marginTop: spacing.sm,
    textAlign: 'center',
  },
});
