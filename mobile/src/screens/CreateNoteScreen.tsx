import { useState } from 'react';
import { KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';

import LocationCaptureField, {
  type CapturedContributionLocation,
} from '../components/LocationCaptureField';
import { AppHeader, Button, Screen } from '../components/ui';
import { createCapture } from '../repositories/captureRepository';
import { colors, spacing, type } from '../theme/theme';
import type { LocalGuide } from '../types/models';

type Props = {
  guide: LocalGuide;
  onDone: () => void;
};

export default function CreateNoteScreen({ guide, onDone }: Props) {
  const db = useSQLiteContext();
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [location, setLocation] = useState<CapturedContributionLocation | null>(null);

  async function handleSave() {
    const trimmed = text.trim();
    if (!trimmed) {
      setError('Please enter a note before saving.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createCapture(
        db,
        guide.id,
        'note',
        trimmed,
        location
          ? {
              latitude: location.latitude,
              longitude: location.longitude,
              locationSource: location.locationSource,
              locationAccuracyMeters: location.accuracyMeters,
              locationCapturedAt: location.capturedAt,
              locationLabel: location.label,
              externalPlaceId: location.externalPlaceId,
            }
          : {}
      );
      onDone();
    } catch (err) {
      console.error('[CreateNoteScreen] Failed to save local note:', err);
      setError('Could not save this note on your device. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen>
        <AppHeader title="New note" subtitle='e.g. "Heavy snow near the bridge"' onBack={onDone} />

        <TextInput
          style={styles.textArea}
          placeholder="Describe what you observed…"
          placeholderTextColor={colors.inkFaint}
          value={text}
          onChangeText={setText}
          multiline
          numberOfLines={8}
          autoFocus
          editable={!saving}
        />

        <View style={styles.locationWrap}>
          <LocationCaptureField
            value={location}
            onChange={setLocation}
            disabled={saving}
            hint="Optional — capture where you are so this note is tied to the right place."
          />
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Button label={saving ? 'Saving…' : 'Save note'} onPress={handleSave} loading={saving} />

        <Text style={styles.footnote}>
          Stored only on this device, marked "waiting to send" until you sync.
        </Text>
      </Screen>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  textArea: {
    backgroundColor: colors.paperElevated,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: spacing.md,
    ...type.body,
    color: colors.ink,
    minHeight: 180,
    textAlignVertical: 'top',
    marginBottom: spacing.md,
  },
  locationWrap: { marginBottom: spacing.md },
  error: { ...type.small, color: colors.fix, marginBottom: spacing.sm },
  footnote: { ...type.caption, color: colors.inkFaint, marginTop: spacing.md, lineHeight: 17, textAlign: 'center' },
});
