import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { ApiError, NetworkError } from '../api/client';
import { describeCandidateKind, type PlaceCandidate } from '../api/placeCandidates';
import { listPopularQuestions, type GuidePlaceQuestions, type PlaceQuestion } from '../api/placeQuestions';
import { listAssignedQuestions, type Question } from '../api/questions';
import { placeQuestionKindIcon } from '../explore/placeQuestionPrompts';
import {
  Badge,
  type BadgeTone,
  Card,
  EmptyState,
  ErrorState,
  RewardChip,
  Screen,
  SectionHeader,
} from '../components/ui';
import { usePullToRefresh } from '../hooks/usePullToRefresh';
import { listAnswersForGuide } from '../repositories/answerRepository';
import { getAnsweredPlaceQuestionStatuses } from '../repositories/captureRepository';
import { colors, radii, spacing, type } from '../theme/theme';
import type { LocalAnswer, LocalGuide, SyncStatus } from '../types/models';

type Props = {
  guide: LocalGuide;
  /** The place the guide CHOSE. Drives which place questions load — the whole
   * point of the selection step is that this is NOT re-derived from GPS. */
  place: PlaceCandidate | null;
  onChangePlace: () => void;
  onSelectQuestion: (question: Question) => void;
  /** Popular questions are answered through the same screen, but carry a
   * different id space and sync endpoint — see LocalAnswer.questionKind. */
  onSelectPopularQuestion: (question: PlaceQuestion, placeName: string | null) => void;
  /** Lifts the "needs attention" count up to RootNavigator for the tab badge
   * — this screen is the single source of truth for the server's question
   * list, so nothing else re-fetches it. Counts ONLY priority questions:
   * popular questions are optional and must never nag with a badge. */
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
  const answered = question.assignment?.status === 'completed' || localAnswer?.syncStatus === 'uploaded';

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
        {/* Reward is hidden once answered — it's an invitation, not a receipt. */}
        {!answered && question.rewardPoints > 0 ? (
          <RewardChip points={question.rewardPoints} />
        ) : null}
      </View>
    </Card>
  );
}

/**
 * Location-specific contribution rows use a deliberately LIGHTER treatment
 * than the priority queue above them: a flat tinted row rather than an
 * elevated card, no status badges, no urgency language. That visual
 * difference is the whole point — these are optional invitations tied to
 * where the guide happens to be standing, not work the knowledge system has
 * decided it needs from this guide.
 *
 * The icon reflects the CONTRIBUTION KIND (camera for a photo ask, mic for a
 * voice ask, and so on) rather than a generic bullet, and the context note —
 * when research actually found one — renders as a small second line so the
 * invitation reads as "here's why this place is worth reporting on", not a
 * bare question out of nowhere.
 */
function PopularQuestionRow({
  question,
  localAnswer,
  captureStatus,
  onPress,
}: {
  question: PlaceQuestion;
  localAnswer: LocalAnswer | null;
  /** Sync status of an Explore contribution made against this place question,
   * if there is one — the path most place answers actually take. */
  captureStatus: SyncStatus | null;
  onPress: () => void;
}) {
  // A place question can be answered through EITHER path: the answer composer
  // (a local_answer row) or the Explore composer (a capture carrying
  // place_question_id). Only checking the first meant every answer given the
  // normal way looked unanswered forever, so the guide got no acknowledgement
  // and could keep re-answering the same question.
  const status = localAnswer?.syncStatus ?? captureStatus;
  const answered = status != null;
  const sent = status === 'uploaded' || status === 'synced';

  // Once answered the row stops being tappable, matching what
  // AnswerQuestionScreen already enforces for the other question source
  // ("there is no edit/re-answer flow"). Before this, an answered row still
  // opened an empty composer with no sign the guide had already replied, and
  // saving created a SECOND contribution against the same question.
  const Row = answered ? View : Pressable;
  const rowProps = answered
    ? { style: [styles.popularRow, styles.popularRowAnswered] }
    : {
        onPress,
        accessibilityRole: 'button' as const,
        accessibilityLabel: question.questionText,
        style: ({ pressed }: { pressed: boolean }) => [
          styles.popularRow,
          pressed && styles.popularRowPressed,
        ],
      };

  return (
    <Row {...rowProps}>
      <View style={styles.popularIcon}>
        <Ionicons
          name={
            !answered
              ? placeQuestionKindIcon(question.contributionKind)
              : status === 'failed'
                ? 'alert-circle-outline'
                : sent
                  ? 'checkmark-circle'
                  : 'cloud-upload-outline'
          }
          size={17}
          color={
            !answered
              ? colors.inkSoft
              : status === 'failed'
                ? colors.fix
                : sent
                  ? colors.ok
                  : colors.info
          }
        />
      </View>
      <View style={styles.popularBody}>
        <Text style={styles.popularText}>{question.questionText}</Text>
        {!answered && question.contextNote ? (
          <Text style={styles.popularContextNote} numberOfLines={2}>
            {question.contextNote}
          </Text>
        ) : null}
        <View style={styles.popularMetaRow}>
          {answered ? (
            // Distinguishes "on the server" from "still on this phone" rather
            // than calling both of them done -- the same honesty the rest of
            // the app applies to sync state.
            <Text
              style={
                status === 'failed'
                  ? styles.popularAnsweredFailed
                  : sent
                    ? styles.popularAnswered
                    : styles.popularAnsweredPending
              }
            >
              {status === 'failed'
                ? 'You answered this — send failed, will retry'
                : sent
                  ? 'You answered this'
                  : 'You answered this — waiting to send'}
            </Text>
          ) : question.rewardPoints > 0 ? (
            <RewardChip points={question.rewardPoints} />
          ) : null}
        </View>
      </View>
      {!answered ? <Ionicons name="chevron-forward" size={16} color={colors.inkFaint} /> : null}
    </Row>
  );
}

export default function QuestionsScreen({
  guide,
  place,
  onChangePlace,
  onSelectQuestion,
  onSelectPopularQuestion,
  onCountChange,
  refreshKey,
}: Props) {
  const db = useSQLiteContext();
  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [popular, setPopular] = useState<GuidePlaceQuestions | null>(null);
  const [localAnswers, setLocalAnswers] = useState<LocalAnswer[]>([]);
  const [answeredPlaceQuestions, setAnsweredPlaceQuestions] = useState<Map<string, SyncStatus>>(
    new Map()
  );
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
      const [result, answers, placeAnswered] = await Promise.all([
        listAssignedQuestions(guide.serverGuideId),
        listAnswersForGuide(db, guide.id),
        getAnsweredPlaceQuestionStatuses(db, guide.id),
      ]);
      setQuestions(result);
      setLocalAnswers(answers);
      setAnsweredPlaceQuestions(placeAnswered);
      onCountChange(result.filter((q) => q.assignment && q.assignment.status !== 'completed').length);
    } catch (err) {
      const message =
        err instanceof ApiError || err instanceof NetworkError ? err.message : 'Could not load assigned questions.';
      setError(message);
    } finally {
      setLoading(false);
    }

    // Popular questions load SEPARATELY and never affect `error` or the tab
    // badge: they are a secondary source, so a failure here must degrade to
    // "no popular questions" rather than break the priority queue's screen.
    try {
      // Scoped to the CHOSEN place. Without this id the backend falls back to
      // resolving the guide's position, which is precisely the behaviour the
      // selection step exists to replace.
      setPopular(await listPopularQuestions(guide.serverGuideId, place?.id ?? null));
    } catch {
      setPopular(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [db, guide.id, guide.serverGuideId, place?.id]);

  useEffect(() => {
    refresh();
  }, [refresh, refreshKey]);

  // Spinner shows only for a real pull; background loads use the inline
  // "Loading questions…" state below.
  const { pulling, onPull } = usePullToRefresh(refresh);

  const needsAttention = questions?.filter((q) => q.assignment?.status !== 'completed') ?? [];
  const answered = questions?.filter((q) => q.assignment?.status === 'completed') ?? [];

  // The two asks this tab exists for, split by SOURCE -- which is also the
  // split the guide experiences:
  //
  //   About This Place -> Google identified the POI, Perplexity researched it,
  //                       Claude wrote the questions. Always shown while the
  //                       guide is at a place we know something about.
  //   Still True?      -> the knowledge pipeline's own asks: information that
  //                       has aged or gaps it wants closed.
  //
  // `researchStale` is NOT the axis here. It describes how old our RESEARCH
  // about a place is -- an internal refresh schedule -- not whether the guide
  // should be asked about the place at all. Routing on it made the whole
  // "About this place" section vanish whenever a refresh happened to be due,
  // which is exactly backwards: those are still the questions about where
  // they are standing. It now only annotates the section (below).
  const placeQuestions = popular?.questions ?? [];
  const researchAged = popular?.researchStale ?? false;
  const needsChecking = needsAttention.length;
  const hasAnything = (questions?.length ?? 0) > 0 || placeQuestions.length > 0;

  return (
    <Screen
      scroll={hasAnything}
      contentContainerStyle={hasAnything ? undefined : styles.emptyContainer}
      onRefresh={guide.serverGuideId ? onPull : undefined}
      refreshing={pulling}
    >
      <View style={styles.header}>
        <Text style={styles.title}>Questions</Text>
        <Text style={styles.subtitle}>
          About the place you chose, and what needs checking again.
        </Text>
      </View>

      {/* Names the chosen subject and offers the way to switch it, so a guide
          looking at unexpected questions can see WHY and fix it in one tap
          instead of assuming the app is wrong about where they are. */}
      {place ? (
        <Pressable
          onPress={onChangePlace}
          accessibilityRole="button"
          accessibilityLabel={`Questions about ${place.name}. Tap to choose a different place.`}
          style={({ pressed }) => [styles.placeBar, pressed && styles.placeBarPressed]}
        >
          <Ionicons name="location" size={14} color={colors.marigoldDeep} />
          <View style={styles.placeBarText}>
            <Text style={styles.placeBarName} numberOfLines={1}>
              {place.name}
            </Text>
            {describeCandidateKind(place) ? (
              <Text style={styles.placeBarKind}>{describeCandidateKind(place)}</Text>
            ) : null}
          </View>
          <Text style={styles.placeBarChange}>Change</Text>
        </Pressable>
      ) : null}

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
      ) : !hasAnything ? (
        <EmptyState
          icon="chatbubbles-outline"
          title="No questions right now"
          message="You're all caught up. Pull down or come back later to check for new ones."
        />
      ) : (
        <View style={styles.list}>
          {/* ── 1. ABOUT THIS PLACE ──────────────────────────────────────
              Researched questions about the POI the guide is standing at.
              First because they are the most specific thing this tab can
              ask: nobody who is not here can answer them. */}
          {placeQuestions.length > 0 ? (
            <View style={styles.popularSection}>
              <SectionHeader
                title="About this place"
                meta={
                  popular?.distanceMeters != null
                    ? `~${Math.round(popular.distanceMeters)}m away`
                    : undefined
                }
              />
              <Text style={styles.popularIntro}>
                {popular?.locationName
                  ? `You're at ${popular.locationName}. These are specific to here — answer any you can see the answer to right now.`
                  : "These are specific to where you are — answer any you can see the answer to right now."}
                {researchAged
                  ? ' Some of this was researched a while ago, so it is worth a second look.'
                  : ''}
              </Text>
              <View style={styles.popularGroup}>
                {placeQuestions.map((q) => (
                  <PopularQuestionRow
                    key={q.id}
                    question={q}
                    localAnswer={localAnswers.find((a) => a.serverQuestionId === q.id) ?? null}
                    captureStatus={answeredPlaceQuestions.get(q.id) ?? null}
                    onPress={() => onSelectPopularQuestion(q, popular?.locationName ?? null)}
                  />
                ))}
              </View>
            </View>
          ) : null}

          {/* ── 2. STILL TRUE? / KNOWLEDGE GAPS ──────────────────────────
              The knowledge pipeline's own asks: information it holds that has
              aged out, and gaps it wants closed. Distinct from the section
              above by SOURCE and by job -- those describe a place we just
              identified, these confirm or correct something the system
              already believes. */}
          {needsAttention.length > 0 ? (
            <View style={styles.popularSection}>
              <SectionHeader title="Still true?" meta={String(needsChecking)} />
              <Text style={styles.popularIntro}>
                Information we already hold that has aged, or gaps we know about. A quick
                confirmation keeps it accurate for everyone who comes next.
              </Text>
              {needsAttention.map((q) => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  localAnswer={localAnswers.find((a) => a.serverQuestionId === q.id) ?? null}
                  onPress={() => onSelectQuestion(q)}
                />
              ))}
            </View>
          ) : null}

          {answered.length > 0 ? (
            <View style={styles.answeredSection}>
              <SectionHeader title="Answered" meta={String(answered.length)} />
              {answered.map((q) => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  localAnswer={localAnswers.find((a) => a.serverQuestionId === q.id) ?? null}
                  onPress={() => onSelectQuestion(q)}
                />
              ))}
            </View>
          ) : null}
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { marginBottom: spacing.md },
  placeBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.md,
    backgroundColor: colors.marigoldSoft,
    marginBottom: spacing.xs,
  },
  placeBarPressed: { opacity: 0.85 },
  placeBarText: { flex: 1 },
  placeBarName: { ...type.smallBold, color: colors.ink },
  placeBarKind: { ...type.caption, color: colors.inkFaint, marginTop: 1 },
  placeBarChange: { ...type.captionBold, color: colors.marigoldDeep, textDecorationLine: 'underline' },
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

  popularSection: { marginTop: spacing.lg },
  popularIntro: {
    ...type.small,
    color: colors.inkFaint,
    marginTop: -spacing.xxs,
    marginBottom: spacing.sm,
    lineHeight: 18,
  },
  // One grouped, recessed surface rather than N elevated cards — visually
  // subordinate to the priority queue by construction, not just by position.
  popularGroup: {
    backgroundColor: colors.paperMuted,
    borderRadius: radii.lg,
    paddingVertical: spacing.xxs,
    paddingHorizontal: spacing.xxs,
  },
  popularRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.md,
    minHeight: 56,
  },
  popularRowPressed: { backgroundColor: colors.neutralSoft },
  // Answered rows recede rather than disappear: the guide should still be able
  // to see what they already covered here.
  popularRowAnswered: { opacity: 0.7 },
  popularIcon: { width: 26, alignItems: 'center' },
  popularBody: { flex: 1 },
  popularText: { ...type.body, color: colors.ink, lineHeight: 21 },
  popularContextNote: { ...type.caption, color: colors.inkFaint, marginTop: 2, lineHeight: 16 },
  popularMetaRow: { flexDirection: 'row', alignItems: 'center', marginTop: 6 },
  popularAnswered: { ...type.caption, color: colors.ok },
  popularAnsweredPending: { ...type.caption, color: colors.info },
  popularAnsweredFailed: { ...type.caption, color: colors.fix },

  answeredSection: { marginTop: spacing.lg },
});
