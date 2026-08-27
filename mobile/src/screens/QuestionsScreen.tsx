import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { ApiError, NetworkError } from '../api/client';
import { listAssignedQuestions, type Question } from '../api/questions';
import { Badge, type BadgeTone, Card, EmptyState, ErrorState, Screen, SectionHeader } from '../components/ui';
import { usePullToRefresh } from '../hooks/usePullToRefresh';
import { listAnswersForGuide } from '../repositories/answerRepository';
import { colors, spacing, type } from '../theme/theme';
import type { LocalAnswer, LocalGuide } from '../types/models';

type Props = {
  guide: LocalGuide;
  onSelectQuestion: (question: Question) => void;
  /** Lifts the "needs attention" count up to RootNavigator for the tab badge
   * — this screen is the single source of truth for the server's question
   * list, so nothing else re-fetches it. */
  onCountChange: (count: number | null) => void;
  refreshKey: number;
};

/** Truthful, merged progress for one question — never "answered" just
 * because local text exists (Part J/H: only 'uploaded' locally, or
 * 'completed' on the server, counts as truly sent). */
type Progress = { label: string; tone: BadgeTone; icon: keyof typeof Ionicons.glyphMap };

function describeProgress(question: Question, localAnswer: LocalAnswer | null): Progress {
  if (question.assignment?.status === 'completed') {
    return { label: 'Answered', tone: 'success', icon: 'checkmark-circle' };
  }
  if (!localAnswer) {
    return { label: 'Needs your input', tone: 'warning', icon: 'ellipse-outline' };
  }
  switch (localAnswer.syncStatus) {
    case 'uploaded':
      return { label: 'Answered', tone: 'success', icon: 'checkmark-circle' };
    case 'uploading':
      return { label: 'Sending…', tone: 'info', icon: 'sync-outline' };
    case 'failed':
      return { label: 'Send failed — will retry', tone: 'danger', icon: 'alert-circle-outline' };
    default:
      return { label: 'Saved — waiting to send', tone: 'info', icon: 'cloud-upload-outline' };
  }
}

/** Plain-language framing for the gap state — used only where it genuinely
 * helps convey urgency, never exposing backend ranking mechanics. */
function gapStateBadge(question: Question): { label: string; tone: BadgeTone } | null {
  if (question.assignment?.status === 'completed') return null;
  switch (question.gapState) {
    case 'missing':
      return { label: 'No report yet', tone: 'neutral' };
    case 'aging':
      return { label: 'Getting old', tone: 'neutral' };
    case 'stale':
      return { label: 'Update needed', tone: 'warning' };
    default:
      return null;
  }
}

function QuestionCard({
  question,
  localAnswer,
  onPress,
}: {
  question: Question;
  localAnswer: LocalAnswer | null;
  onPress: () => void;
}) {
  const progress = describeProgress(question, localAnswer);
  const gapBadge = gapStateBadge(question);

  return (
    <Card onPress={onPress} accessibilityLabel={question.questionText ?? question.displayName} style={styles.card}>
      <View style={styles.cardHeaderRow}>
        <Text style={styles.topic}>{question.displayName}</Text>
        {question.safetyCritical ? <Badge label="Safety" tone="danger" icon="warning-outline" /> : null}
      </View>

      <Text style={styles.questionText} numberOfLines={4}>
        {question.questionText}
      </Text>

      {question.nearestKnownPlaceName ? (
        <View style={styles.placeRow}>
          <Ionicons name="location-outline" size={13} color={colors.inkFaint} />
          <Text style={styles.placeText} numberOfLines={1}>
            Near {question.nearestKnownPlaceName}
            {question.nearestKnownPlaceDistanceMeters != null
              ? ` (~${Math.round(question.nearestKnownPlaceDistanceMeters)}m)`
              : ''}
          </Text>
        </View>
      ) : null}

      <View style={styles.badgeRow}>
        <Badge label={progress.label} tone={progress.tone} icon={progress.icon} />
        {gapBadge ? <Badge label={gapBadge.label} tone={gapBadge.tone} /> : null}
      </View>
    </Card>
  );
}

export default function QuestionsScreen({ guide, onSelectQuestion, onCountChange, refreshKey }: Props) {
  const db = useSQLiteContext();
  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [localAnswers, setLocalAnswers] = useState<LocalAnswer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!guide.serverGuideId) {
      onCountChange(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [result, answers] = await Promise.all([
        listAssignedQuestions(guide.serverGuideId),
        listAnswersForGuide(db, guide.id),
      ]);
      setQuestions(result);
      setLocalAnswers(answers);
      onCountChange(result.filter((q) => q.assignment && q.assignment.status !== 'completed').length);
    } catch (err) {
      const message =
        err instanceof ApiError || err instanceof NetworkError ? err.message : 'Could not load assigned questions.';
      setError(message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [db, guide.id, guide.serverGuideId]);

  useEffect(() => {
    refresh();
  }, [refresh, refreshKey]);

  // Spinner shows only for a real pull; background loads use the inline
  // "Loading questions…" state below.
  const { pulling, onPull } = usePullToRefresh(refresh);

  const needsAttention = questions?.filter((q) => q.assignment?.status !== 'completed') ?? [];
  const answered = questions?.filter((q) => q.assignment?.status === 'completed') ?? [];

  return (
    <Screen
      scroll={!!questions?.length}
      contentContainerStyle={questions?.length ? undefined : styles.emptyContainer}
      onRefresh={guide.serverGuideId ? onPull : undefined}
      refreshing={pulling}
    >
      <View style={styles.header}>
        <Text style={styles.title}>Questions</Text>
        <Text style={styles.subtitle}>Sent by the server when it needs a report from your area.</Text>
      </View>

      {!guide.serverGuideId ? (
        <EmptyState
          icon="cloud-offline-outline"
          title="Sync your profile first"
          message="Questions can be checked once your guide profile has synced with the server."
        />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} retrying={loading} />
      ) : loading && questions === null ? (
        <View style={styles.loadingWrap}>
          <EmptyState icon="hourglass-outline" title="Loading questions…" />
        </View>
      ) : questions && questions.length === 0 ? (
        <EmptyState
          icon="chatbubbles-outline"
          title="No questions right now"
          message="You're all caught up. Pull down or come back later to check for new ones."
        />
      ) : (
        <View style={styles.list}>
          {needsAttention.length > 0 ? (
            <>
              <SectionHeader title="Needs your input" meta={String(needsAttention.length)} />
              {needsAttention.map((q) => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  localAnswer={localAnswers.find((a) => a.serverQuestionId === q.id) ?? null}
                  onPress={() => onSelectQuestion(q)}
                />
              ))}
            </>
          ) : null}

          {answered.length > 0 ? (
            <>
              <SectionHeader title="Answered" meta={String(answered.length)} />
              {answered.map((q) => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  localAnswer={localAnswers.find((a) => a.serverQuestionId === q.id) ?? null}
                  onPress={() => onSelectQuestion(q)}
                />
              ))}
            </>
          ) : null}
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { marginBottom: spacing.md },
  title: { ...type.display, fontSize: 26, color: colors.ink },
  subtitle: { ...type.small, color: colors.inkFaint, marginTop: 4 },
  loadingWrap: { marginTop: spacing.xl },
  emptyContainer: { flexGrow: 1 },
  list: { paddingBottom: spacing.lg },
  card: { marginBottom: spacing.sm },
  cardHeaderRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: spacing.xs },
  topic: { ...type.captionBold, color: colors.inkFaint, letterSpacing: 0.4, textTransform: 'uppercase', flexShrink: 1 },
  questionText: { ...type.body, color: colors.ink, marginTop: 6, marginBottom: spacing.xs },
  placeRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: spacing.xs },
  placeText: { ...type.caption, color: colors.inkFaint, flexShrink: 1 },
  badgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: 4 },
});
