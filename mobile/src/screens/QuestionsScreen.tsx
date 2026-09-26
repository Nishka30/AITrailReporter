import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { ApiError, NetworkError } from '../api/client';
import { describeCandidateKind, type PlaceCandidate } from '../api/placeCandidates';
import { listPopularQuestions, type GuidePlaceQuestions, type PlaceQuestion } from '../api/placeQuestions';
import { claimQuestion, listAssignedQuestions, listRelevantQuestions, type Question } from '../api/questions';
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

/** Groups "About this place" questions by their PRIMARY (category-driven)
 * category, when they have one -- preserving each question's own order
 * within its group. Ungrouped questions (predate this feature, or a curated
 * seed question with no category) fall into a single trailing bucket with no
 * heading, rendering exactly as before. Purely a display grouping: it
 * doesn't touch what's fetched, claimed or answered. */
type PlaceQuestionGroup = { key: string; label: string | null; questions: PlaceQuestion[] };

function groupPlaceQuestionsByCategory(questions: PlaceQuestion[]): PlaceQuestionGroup[] {
  const groups = new Map<string, PlaceQuestionGroup>();
  const order: string[] = [];
  for (const q of questions) {
    const key = q.categorySlug ?? '__ungrouped__';
    if (!groups.has(key)) {
      groups.set(key, { key, label: q.categoryDisplayName, questions: [] });
      order.push(key);
    }
    groups.get(key)!.questions.push(q);
  }
  return order.map((k) => groups.get(k)!);
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
        {!answered && question.isReverification ? (
          <Text style={styles.popularReverificationLabel}>CHECKING IN</Text>
        ) : null}
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
  // Whether the PLACE-scoped fetch (the one behind Google -> Perplexity ->
  // Claude research) has completed at least once for the current place.
  // Tracked separately from `questions === null` because the two data
  // sources finish independently -- without this, the screen fell through to
  // "No questions right now" as soon as the (fast, place-independent)
  // assigned-questions fetch resolved, even while the place-specific research
  // was still in flight. Reset to false whenever the chosen place changes, so
  // a new place gets its own honest loading state rather than reusing the
  // previous place's.
  const [popularLoaded, setPopularLoaded] = useState(false);
  // Existing, already-generated knowledge-gap questions near the CHOSEN
  // place (proximity feature) -- a third, independent source again, same
  // reasoning as popularLoaded: it can genuinely still be in flight after
  // the assigned-questions fetch resolves, and a place change deserves its
  // own fresh "have we heard back yet?" state.
  const [relevant, setRelevant] = useState<Question[]>([]);
  const [relevantLoaded, setRelevantLoaded] = useState(false);
  // The one relevant-question card currently being claimed (auto-claim on
  // view) -- guards against a double-tap firing two claim requests for the
  // same question while the first is still in flight.
  const [claimingId, setClaimingId] = useState<string | null>(null);

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
    } finally {
      // Marks THIS data source as having reported in at least once, whatever
      // the outcome -- see popularLoaded's own comment for why this can't
      // just be `questions === null` (that guards the OTHER fetch).
      setPopularLoaded(true);
    }

    // Proximity-relevant questions load separately too, same "own try/catch,
    // own loaded flag, never touches `error`/the badge" pattern as popular
    // questions above -- and only when a place is actually chosen, since
    // there is nothing to be near otherwise (no fan-out to raw GPS, no
    // continuous tracking, matching the existing selectedPlace-only model).
    if (place?.id) {
      try {
        setRelevant(await listRelevantQuestions(place.id));
      } catch {
        setRelevant([]);
      } finally {
        setRelevantLoaded(true);
      }
    } else {
      setRelevant([]);
      setRelevantLoaded(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [db, guide.id, guide.serverGuideId, place?.id]);

  useEffect(() => {
    refresh();
  }, [refresh, refreshKey]);

  // A new chosen place deserves its own honest "have we heard back yet?"
  // state, not a leftover `true` from whatever was selected before. `refresh`
  // above already re-runs on a place change (place?.id is one of its deps),
  // so this only needs to clear the flag -- the effect above puts it back.
  useEffect(() => {
    setPopularLoaded(false);
    setRelevantLoaded(false);
  }, [place?.id]);

  // Auto-claim on view: makes the tapping guide the current assignee of a
  // proximity-surfaced question (server-side reassignment if someone else
  // held it and hadn't answered) so the existing, unmodified answer flow
  // just works -- see backend/app/services/question_answers.py::
  // claim_question. Skipped entirely when this guide already holds the
  // current assignment (the common case once they've claimed it once).
  const handleSelectRelevantQuestion = useCallback(
    async (question: Question) => {
      if (!guide.serverGuideId || claimingId) return;
      if (question.assignment?.guideId === guide.serverGuideId) {
        onSelectQuestion(question);
        return;
      }
      setClaimingId(question.id);
      try {
        const claimed = await claimQuestion(question.id, guide.serverGuideId);
        onSelectQuestion(claimed);
      } catch {
        // Someone else finished answering it between the list read and this
        // tap (a real, accepted race -- see claim_question's own docstring)
        // -- refresh instead of opening a now-stale answer screen.
        await refresh();
      } finally {
        setClaimingId(null);
      }
    },
    [guide.serverGuideId, claimingId, onSelectQuestion, refresh]
  );

  // Spinner shows only for a real pull; background loads use the inline
  // "Loading questions…" state below.
  const { pulling, onPull } = usePullToRefresh(refresh);

  const rawNeedsAttention = questions?.filter((q) => q.assignment?.status !== 'completed') ?? [];
  const answered = questions?.filter((q) => q.assignment?.status === 'completed') ?? [];

  // Dedup rule (stable id, never question text): a question already shown
  // under Location-Specific Questions never repeats under Still True? --
  // Location-Specific claims it first since it's the more specific reason
  // it's being asked right now.
  const relevantIds = new Set(relevant.map((q) => q.id));
  const needsAttention = rawNeedsAttention.filter((q) => !relevantIds.has(q.id));

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

  // A place was resolved (GPS or chosen), the backend says its research is
  // due/never-run, and it has produced zero questions YET. This is the
  // in-progress state of the Google -> Perplexity -> Claude pipeline, not a
  // final answer -- `researchAged` only clears once that pipeline actually
  // completes (place_questions.py sets researched_at on success), so once it
  // does, this flips to false on its own and either real questions or a
  // genuine "no questions" result takes over. Gated on `popularLoaded` so it
  // is never true before the FIRST response for this place has even arrived.
  const stillResearching =
    popularLoaded && popular?.locationId != null && researchAged && placeQuestions.length === 0;

  // Counts as "something to show" even with an empty list: a calm
  // "researching…" message is the honest state here, not the same
  // "No questions right now" shown when there is truly nothing left to ask.
  const hasAnything =
    (questions?.length ?? 0) > 0 || placeQuestions.length > 0 || relevant.length > 0 || stillResearching;

  // Bounded, self-terminating auto-refresh while research is in flight -- an
  // optimization, not a requirement: the pipeline runs regardless of whether
  // anyone is polling it (see backend/app/api/routes/guides.py's
  // background.add_task), and a guide can always pull-to-refresh instead.
  // This just means most guides never have to.
  //
  // Capped at a handful of attempts a few seconds apart rather than polling
  // indefinitely -- a slow or stuck run should settle into the researching
  // message rather than spin forever. Each attempt is a plain GET; repeating
  // it while a run is already 'processing' is a no-op server-side (see
  // ensure_researched's SELECT ... FOR UPDATE guard), so this never causes a
  // second research run to start.
  const researchPoll = useRef<{ timer: ReturnType<typeof setTimeout> | null; attempts: number }>({
    timer: null,
    attempts: 0,
  });

  useEffect(() => {
    // A newly chosen place gets its own fresh attempt budget -- not
    // whatever was left over from the place before it.
    researchPoll.current.attempts = 0;
    if (researchPoll.current.timer) {
      clearTimeout(researchPoll.current.timer);
      researchPoll.current.timer = null;
    }
  }, [place?.id]);

  useEffect(() => {
    const MAX_ATTEMPTS = 6;
    const POLL_DELAY_MS = 4000;
    if (!stillResearching || researchPoll.current.attempts >= MAX_ATTEMPTS) {
      return undefined;
    }
    const timer = setTimeout(() => {
      researchPoll.current.attempts += 1;
      refresh();
    }, POLL_DELAY_MS);
    researchPoll.current.timer = timer;
    return () => clearTimeout(timer);
  }, [stillResearching, refresh]);

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
      ) : loading && (questions === null || !popularLoaded || !relevantLoaded) ? (
        // Stays up until ALL THREE sources have reported in at least once
        // for this place -- the assigned-questions fetch (fast, place-
        // independent), the place-scoped research pipeline, and the
        // proximity-relevant gap-questions read (fast, but must not race
        // ahead and claim "no questions" before it's actually answered).
        // Previously this only waited on the first two, so the screen could
        // flip to "No questions right now" while a source was still in
        // flight.
        <View style={styles.loadingWrap}>
          <EmptyState
            icon="hourglass-outline"
            title={
              place && (!popularLoaded || !relevantLoaded)
                ? 'Finding questions for this location…'
                : 'Loading questions…'
            }
          />
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
              {groupPlaceQuestionsByCategory(placeQuestions).map((group) => (
                <View key={group.key} style={styles.categoryGroupWrap}>
                  {group.label ? (
                    <Text style={styles.categoryGroupLabel}>{group.label}</Text>
                  ) : null}
                  <View style={styles.popularGroup}>
                    {group.questions.map((q) => (
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
              ))}
            </View>
          ) : stillResearching ? (
            // The pipeline is genuinely still working, not genuinely empty --
            // see stillResearching's own comment. Same section header as the
            // real thing so this reads as "the same section, not ready yet"
            // rather than a different, unexplained state.
            <View style={styles.popularSection}>
              <SectionHeader title="About this place" />
              <View style={styles.researchingRow}>
                <Ionicons name="sparkles-outline" size={17} color={colors.marigoldDeep} />
                <View style={styles.researchingTextWrap}>
                  <Text style={styles.researchingTitle}>Researching this location…</Text>
                  <Text style={styles.researchingBody}>
                    {popular?.locationName
                      ? `We're looking up what's worth asking about ${popular.locationName}.`
                      : "We're looking up what's worth asking about this place."}{' '}
                    This usually takes under a minute — pull down to check again sooner.
                  </Text>
                </View>
              </View>
            </View>
          ) : null}

          {/* ── 1.5 LOCATION-SPECIFIC QUESTIONS ──────────────────────────
              Existing, already-generated knowledge-gap questions near the
              chosen place -- distinct from "About this place" above (that's
              AI-researched web content; this is the SAME knowledge-gap
              system as "Still true?" below, just filtered to this place
              instead of this guide's own assignments). Never generates
              anything here -- if it's not already a persisted question, it
              simply doesn't show up. */}
          {relevant.length > 0 ? (
            <View style={styles.popularSection}>
              <SectionHeader title="Location-Specific Questions" meta={String(relevant.length)} />
              <Text style={styles.popularIntro}>
                {place
                  ? `Existing questions near ${place.name} that could use a fresh answer.`
                  : 'Existing questions near here that could use a fresh answer.'}
              </Text>
              {relevant.map((q) => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  localAnswer={localAnswers.find((a) => a.serverQuestionId === q.id) ?? null}
                  onPress={() => handleSelectRelevantQuestion(q)}
                />
              ))}
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
  // Same recessed treatment as popularGroup below -- reads as "this section,
  // not ready yet" rather than a visually different, alarming state.
  researchingRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    backgroundColor: colors.paperMuted,
    borderRadius: radii.lg,
    padding: spacing.md,
  },
  researchingTextWrap: { flex: 1 },
  researchingTitle: { ...type.smallBold, color: colors.ink },
  researchingBody: { ...type.caption, color: colors.inkFaint, marginTop: 3, lineHeight: 17 },
  // One grouped, recessed surface rather than N elevated cards — visually
  // subordinate to the priority queue by construction, not just by position.
  popularGroup: {
    backgroundColor: colors.paperMuted,
    borderRadius: radii.lg,
    paddingVertical: spacing.xxs,
    paddingHorizontal: spacing.xxs,
  },
  categoryGroupWrap: { marginBottom: spacing.sm },
  categoryGroupLabel: {
    ...type.captionBold,
    color: colors.inkFaint,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
    marginBottom: 4,
    marginLeft: 2,
  },
  popularReverificationLabel: {
    ...type.captionBold,
    color: colors.marigoldDeep,
    letterSpacing: 0.3,
    marginBottom: 1,
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
