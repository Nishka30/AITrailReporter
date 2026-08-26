import { useCallback, useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import type { Question } from '../api/questions';
import { AppHeader, Badge, Button, Card, LoadingState, Screen } from '../components/ui';
import { createAnswer, getAnswerByQuestionId } from '../repositories/answerRepository';
import { colors, spacing, type } from '../theme/theme';
import type { LocalAnswer, LocalGuide } from '../types/models';

type Props = {
  guide: LocalGuide;
  question: Question;
  onDone: () => void;
};

function gapContextLabel(question: Question): string | null {
  if (question.assignment?.status === 'completed') return null;
  switch (question.gapState) {
    case 'missing':
      return 'No report yet from this area';
    case 'aging':
      return 'Getting old — a quick confirmation helps';
    case 'stale':
      return 'The last report here is out of date';
    default:
      return null;
  }
}

/**
 * Answer composition for one assigned question (Step 13, restyled Step 15).
 * Offline-first, unchanged: saving writes to SQLite immediately and returns
 * — it never waits on, or depends on, a network response. The answer enters
 * the existing sync engine (src/sync/syncService.ts) and is uploaded next
 * time "Sync now" runs, exactly like a note or a location.
 *
 * If this question was already answered on this device (regardless of
 * whether that answer has synced yet), the compose form is never shown
 * again -- there is no edit/re-answer flow (see
 * backend/app/services/question_answers.py: one answer per assignment).
 */
export default function AnswerQuestionScreen({ guide, question, onDone }: Props) {
  const db = useSQLiteContext();
  const [existingAnswer, setExistingAnswer] = useState<LocalAnswer | null | undefined>(undefined);
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  const loadExisting = useCallback(async () => {
    try {
      const answer = await getAnswerByQuestionId(db, question.id);
      setExistingAnswer(answer);
    } catch (err) {
      console.error('[AnswerQuestionScreen] Failed to read local answer:', err);
      setExistingAnswer(null);
    }
  }, [db, question.id]);

  useEffect(() => {
    loadExisting();
  }, [loadExisting]);

  async function handleSave() {
    const trimmed = text.trim();
    if (!trimmed) {
      setError('Please enter an answer before saving.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createAnswer(db, guide.id, question.id, trimmed, new Date().toISOString());
      setJustSaved(true);
      await loadExisting();
    } catch (err) {
      console.error('[AnswerQuestionScreen] Failed to save local answer:', err);
      setError('Could not save this answer on your device. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  const alreadyAnsweredOnServer = question.assignment?.status === 'completed' || !!question.answer;
  const gapContext = gapContextLabel(question);

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen>
        <AppHeader title={question.displayName} onBack={onDone} />

        <Card style={styles.questionCard}>
          <View style={styles.badgeRow}>
            {question.safetyCritical ? <Badge label="Safety" tone="danger" icon="warning-outline" /> : null}
            {gapContext ? <Badge label={gapContext} tone="neutral" /> : null}
          </View>
          <Text style={styles.questionText}>{question.questionText}</Text>
          {question.nearestKnownPlaceName ? (
            <View style={styles.placeRow}>
              <Ionicons name="location-outline" size={13} color={colors.inkFaint} />
              <Text style={styles.placeText}>
                Near {question.nearestKnownPlaceName}
                {question.nearestKnownPlaceDistanceMeters != null
                  ? ` (~${Math.round(question.nearestKnownPlaceDistanceMeters)}m)`
                  : ''}
              </Text>
            </View>
          ) : null}
        </Card>

        {existingAnswer === undefined ? (
          <LoadingState message="Checking for a saved answer…" />
        ) : existingAnswer ? (
          <AnsweredCard answer={existingAnswer} justSaved={justSaved} onDone={onDone} />
        ) : alreadyAnsweredOnServer && question.answer ? (
          <AnsweredElsewhereCard answerText={question.answer.answerText} onDone={onDone} />
        ) : (
          <>
            <Text style={styles.composeLabel}>Your answer</Text>
            <TextInput
              style={styles.textArea}
              placeholder="Type what you see…"
              placeholderTextColor={colors.inkFaint}
              value={text}
              onChangeText={setText}
              multiline
              numberOfLines={6}
              autoFocus
              editable={!saving}
            />

            {error ? <Text style={styles.error}>{error}</Text> : null}

            <Button label={saving ? 'Saving…' : 'Save answer'} onPress={handleSave} loading={saving} />

            <Text style={styles.footnote}>
              Saved on this device right away. It's sent the next time you sync — no connection needed now.
            </Text>
          </>
        )}
      </Screen>
    </KeyboardAvoidingView>
  );
}

function AnsweredCard({
  answer,
  justSaved,
  onDone,
}: {
  answer: LocalAnswer;
  justSaved: boolean;
  onDone: () => void;
}) {
  const status =
    answer.syncStatus === 'uploaded'
      ? { label: 'Sent to the server', tone: 'success' as const, icon: 'checkmark-circle' as const }
      : answer.syncStatus === 'failed'
        ? { label: 'Send failed — will retry on next sync', tone: 'danger' as const, icon: 'alert-circle-outline' as const }
        : answer.syncStatus === 'uploading'
          ? { label: 'Sending…', tone: 'info' as const, icon: 'sync-outline' as const }
          : { label: 'Saved — waiting to send', tone: 'info' as const, icon: 'cloud-upload-outline' as const };

  return (
    <Card variant="outline" style={styles.answeredCard}>
      <Text style={styles.answeredLabel}>{justSaved ? 'Saved!' : 'Your answer'}</Text>
      <Text style={styles.answeredText}>{answer.answerText}</Text>
      <Badge label={status.label} tone={status.tone} icon={status.icon} />
      <View style={styles.doneButtonWrap}>
        <Button label="Back to questions" onPress={onDone} variant="secondary" />
      </View>
    </Card>
  );
}

function AnsweredElsewhereCard({ answerText, onDone }: { answerText: string; onDone: () => void }) {
  return (
    <Card variant="outline" style={styles.answeredCard}>
      <Text style={styles.answeredLabel}>Answer on file</Text>
      <Text style={styles.answeredText}>{answerText}</Text>
      <Badge label="Already answered (another device)" tone="success" icon="checkmark-circle" />
      <View style={styles.doneButtonWrap}>
        <Button label="Back to questions" onPress={onDone} variant="secondary" />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  questionCard: { marginBottom: spacing.md },
  badgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm },
  questionText: { ...type.subtitle, color: colors.ink, lineHeight: 24 },
  placeRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: spacing.sm },
  placeText: { ...type.caption, color: colors.inkFaint },
  composeLabel: { ...type.captionBold, color: colors.inkFaint, letterSpacing: 0.4, marginBottom: spacing.xs },
  textArea: {
    backgroundColor: colors.paperElevated,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: spacing.md,
    ...type.body,
    color: colors.ink,
    minHeight: 140,
    textAlignVertical: 'top',
    marginBottom: spacing.md,
  },
  error: { ...type.small, color: colors.fix, marginBottom: spacing.sm },
  footnote: { ...type.caption, color: colors.inkFaint, marginTop: spacing.md, lineHeight: 17, textAlign: 'center' },
  answeredCard: { alignItems: 'flex-start', gap: spacing.sm },
  answeredLabel: { ...type.captionBold, color: colors.inkFaint, letterSpacing: 0.4 },
  answeredText: { ...type.body, color: colors.ink, lineHeight: 22 },
  doneButtonWrap: { alignSelf: 'stretch', marginTop: spacing.xs },
});
