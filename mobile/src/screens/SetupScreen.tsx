import { useState } from 'react';
import { KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { createLocalGuide } from '../repositories/guideRepository';
import { Button } from '../components/ui';
import { colors, radii, spacing, type } from '../theme/theme';

type Props = {
  onGuideCreated: () => void;
};

export default function SetupScreen({ onGuideCreated }: Props) {
  const db = useSQLiteContext();
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Please enter your name.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createLocalGuide(db, trimmed);
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
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.iconCircle}>
        <Ionicons name="trail-sign-outline" size={30} color={colors.marigoldDeep} />
      </View>

      <Text style={styles.title}>Trail Reporter</Text>
      <Text style={styles.subtitle}>
        Set up your guide profile to get started. This is saved only on this device — no
        internet connection is needed.
      </Text>

      <TextInput
        style={styles.input}
        placeholder="Your name"
        placeholderTextColor={colors.inkFaint}
        value={name}
        onChangeText={setName}
        autoFocus
        editable={!saving}
      />

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Button label={saving ? 'Saving…' : 'Save and continue'} onPress={handleSave} loading={saving} />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: spacing.xl, backgroundColor: colors.paper },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.marigoldSoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  title: { ...type.display, color: colors.ink, marginBottom: spacing.xs },
  subtitle: { ...type.body, color: colors.inkSoft, marginBottom: spacing.xl, lineHeight: 22 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.paperElevated,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    ...type.body,
    color: colors.ink,
    marginBottom: spacing.md,
  },
  error: { ...type.small, color: colors.fix, marginBottom: spacing.md },
});
