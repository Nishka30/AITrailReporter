import { useState } from 'react';
import { Image, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { AppHeader, Badge, Button, Card, Screen } from '../components/ui';
import type { ExplorePrompt } from '../explore/explorePrompts';
import { choosePhoto, takePhoto, type PhotoPickResult } from '../photo/photoPickerService';
import { createExploreCapture } from '../repositories/captureRepository';
import { colors, radii, spacing, type } from '../theme/theme';
import type { LocalGuide } from '../types/models';

type Props = {
  guide: LocalGuide;
  prompt: ExplorePrompt;
  onDone: () => void;
};

type AttachedPhoto = { uri: string; contentType: string };

/**
 * Explore contribution composer (Step 16).
 *
 * Offline-first, exactly like every other capture in this app: saving writes
 * to SQLite and returns — it never waits on, or depends on, a network
 * response. The contribution enters the SAME sync engine
 * (src/sync/syncService.ts) and uploads on the next "Sync now", identical to a
 * note, a voice recording, or a question answer.
 *
 * Text is always required, even when a photo is attached. That is a deliberate
 * product rule, not an oversight: the backend turns TEXT into observations
 * (this step does no image understanding), so a photo-only contribution could
 * never become knowledge. The copy says so plainly rather than accepting a
 * silent dead end.
 */
export default function ExploreContributeScreen({ guide, prompt, onDone }: Props) {
  const db = useSQLiteContext();
  const [text, setText] = useState('');
  const [photo, setPhoto] = useState<AttachedPhoto | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [photoNotice, setPhotoNotice] = useState<string | null>(null);
  const [pickingPhoto, setPickingPhoto] = useState(false);

  function applyPhotoResult(result: PhotoPickResult) {
    switch (result.status) {
      case 'success':
        setPhoto({ uri: result.uri, contentType: result.contentType });
        setPhotoNotice(null);
        break;
      case 'cancelled':
        // Not an error, and not worth a message — the guide chose to back out.
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
      applyPhotoResult(useCamera ? await takePhoto() : await choosePhoto());
    } finally {
      setPickingPhoto(false);
    }
  }

  async function handleSave() {
    if (saving) return;
    const trimmed = text.trim();
    if (!trimmed) {
      setError(
        photo
          ? 'Please add a few words about the photo — the description is what becomes usable knowledge.'
          : 'Please write something before saving.'
      );
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createExploreCapture(db, guide.id, trimmed, {
        localPhotoUri: photo?.uri ?? null,
        photoContentType: photo?.contentType ?? null,
        // Local-only provenance — the backend does not model prompts.
        promptId: prompt.id,
        promptTitle: prompt.title,
      });
      setSaved(true);
    } catch (err) {
      console.error('[ExploreContributeScreen] Failed to save contribution:', err);
      setError('Could not save this on your device. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  if (saved) {
    return (
      <Screen>
        <AppHeader title="Saved" onBack={onDone} />
        <Card variant="outline" style={styles.savedCard}>
          <View style={styles.savedIcon}>
            <Ionicons name="checkmark-circle" size={30} color={colors.ok} />
          </View>
          <Text style={styles.savedTitle}>Saved on this device</Text>
          <Text style={styles.savedBody}>
            {photo
              ? 'Your note and photo are stored safely here. Both are sent the next time you sync.'
              : 'Your discovery is stored safely here. It is sent the next time you sync.'}
          </Text>
          <Badge label="Waiting to send" tone="info" icon="cloud-upload-outline" />
          <View style={styles.savedButton}>
            <Button label="Back to Explore" onPress={onDone} />
          </View>
        </Card>
      </Screen>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <Screen>
        <AppHeader title={prompt.title} onBack={onDone} />

        <Card style={styles.promptCard}>
          <Text style={styles.promptBody}>{prompt.body}</Text>
          {prompt.reason ? (
            <View style={styles.reasonRow}>
              <Ionicons name="information-circle-outline" size={13} color={colors.inkFaint} />
              <Text style={styles.reasonText}>{prompt.reason}</Text>
            </View>
          ) : null}
        </Card>

        <Text style={styles.label}>Your words</Text>
        <TextInput
          style={styles.textArea}
          placeholder={prompt.placeholder}
          placeholderTextColor={colors.inkFaint}
          value={text}
          onChangeText={setText}
          multiline
          numberOfLines={6}
          autoFocus={!prompt.wantsPhoto}
          editable={!saving}
        />

        <Text style={styles.label}>Photo {prompt.wantsPhoto ? '' : '(optional)'}</Text>
        {photo ? (
          <View style={styles.photoWrap}>
            <Image source={{ uri: photo.uri }} style={styles.photoPreview} resizeMode="cover" />
            <Pressable
              onPress={() => setPhoto(null)}
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
              accessibilityLabel="Choose photo"
              disabled={pickingPhoto || saving}
              style={({ pressed }) => [
                styles.photoAction,
                pressed && styles.photoActionPressed,
                (pickingPhoto || saving) && styles.photoActionDisabled,
              ]}
            >
              <Ionicons name="images-outline" size={21} color={colors.marigoldDeep} />
              <Text style={styles.photoActionText}>Choose photo</Text>
            </Pressable>
          </View>
        )}

        {photoNotice ? <Text style={styles.notice}>{photoNotice}</Text> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}

        <View style={styles.saveButton}>
          <Button
            label={saving ? 'Saving…' : 'Save discovery'}
            onPress={handleSave}
            loading={saving}
          />
        </View>

        <Text style={styles.footnote}>
          Saved on this device right away — no connection needed now. Your description is what
          becomes usable knowledge; the photo is kept alongside it.
        </Text>
      </Screen>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  promptCard: { marginBottom: spacing.lg },
  promptBody: { ...type.subtitle, color: colors.ink, lineHeight: 24 },
  reasonRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: spacing.sm },
  reasonText: { ...type.caption, color: colors.inkFaint, flexShrink: 1 },

  label: {
    ...type.captionBold,
    color: colors.inkFaint,
    letterSpacing: 0.4,
    marginBottom: spacing.xs,
    textTransform: 'uppercase',
  },
  textArea: {
    backgroundColor: colors.paperElevated,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    ...type.body,
    color: colors.ink,
    minHeight: 130,
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
  photoPreview: {
    width: '100%',
    height: 210,
    borderRadius: radii.md,
    backgroundColor: colors.paperMuted,
  },
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

  notice: { ...type.small, color: colors.inkSoft, marginTop: spacing.sm },
  error: { ...type.small, color: colors.fix, marginTop: spacing.sm },
  saveButton: { marginTop: spacing.lg },
  footnote: {
    ...type.caption,
    color: colors.inkFaint,
    marginTop: spacing.md,
    lineHeight: 17,
    textAlign: 'center',
  },

  savedCard: { alignItems: 'center', gap: spacing.sm, marginTop: spacing.xl },
  savedIcon: { marginBottom: spacing.xxs },
  savedTitle: { ...type.title, color: colors.ink, textAlign: 'center' },
  savedBody: { ...type.body, color: colors.inkSoft, textAlign: 'center', lineHeight: 22 },
  savedButton: { alignSelf: 'stretch', marginTop: spacing.sm },
});
