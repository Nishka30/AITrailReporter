import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { ApiError, NetworkError } from '../api/client';
import { getGuideContext, type GuideContext } from '../api/guideContext';
import { coverageGaps, getLocationKnowledgeStatus, type CategoryCoverage } from '../api/locationKnowledge';
import {
  describeCandidateDistance,
  describeCandidateKind,
  type PlaceCandidate,
} from '../api/placeCandidates';
import { getRewardConfig, type RewardConfig } from '../api/rewards';
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  RewardChip,
  Screen,
  SectionHeader,
} from '../components/ui';
import {
  FREE_FORM_PROMPT,
  buildPrompts,
  type ExplorePrompt,
} from '../explore/explorePrompts';
import { usePullToRefresh } from '../hooks/usePullToRefresh';
import { countCapturesByStatus } from '../repositories/captureRepository';
import { colors, radii, shadow, spacing, type } from '../theme/theme';
import type { LocalGuide } from '../types/models';

type Props = {
  guide: LocalGuide;
  /** The place the guide CHOSE to contribute to. Non-null by construction:
   * RootNavigator shows the picker before this tab can render. Explore is
   * about this subject, not about whichever POI happens to be nearest. */
  place: PlaceCandidate | null;
  /** Reopens the picker so the guide can switch subject without leaving the
   * tab — they may have walked on, or picked the wrong thing first time. */
  onChangePlace: () => void;
  onStartContribution: (prompt: ExplorePrompt) => void;
  /** Opens the "Share a Memory" composer — a distinct flow from
   * onStartContribution because a memory carries its own location/date
   * provenance workflow, not a device-built or backend-researched prompt. */
  onStartMemory: () => void;
  refreshKey: number;
};

/** Rough "when was this location taken" phrasing. Only ever called with a real
 * timestamp from the backend — never used to imply freshness we don't have. */
function describeAge(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 2) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}

/** Per-kind visual identity. Explore's cards are deliberately more expressive
 * than the Questions queue's — different job, different feel — while staying
 * inside the existing palette rather than introducing new colours. */
const KIND_STYLE: Record<
  ExplorePrompt['kind'],
  { icon: keyof typeof Ionicons.glyphMap; tint: string; wash: string }
> = {
  photo: { icon: 'camera-outline', tint: colors.marigoldDeep, wash: colors.marigoldSoft },
  conditions: { icon: 'eye-outline', tint: colors.info, wash: colors.infoSoft },
  story: { icon: 'book-outline', tint: colors.ok, wash: colors.okSoft },
  discovery: { icon: 'compass-outline', tint: colors.marigoldDeep, wash: colors.marigoldSoft },
  culture: { icon: 'sparkles-outline', tint: colors.ok, wash: colors.okSoft },
  local_find: { icon: 'restaurant-outline', tint: colors.info, wash: colors.infoSoft },
};

function PromptCard({
  prompt,
  rewardPoints,
  onPress,
}: {
  prompt: ExplorePrompt;
  /** From the backend's reward config; null when it hasn't loaded (offline,
   * or the request failed), in which case no reward is shown at all rather
   * than a guessed number. */
  rewardPoints: number | null;
  onPress: () => void;
}) {
  const style = KIND_STYLE[prompt.kind];
  return (
    <Card onPress={onPress} accessibilityLabel={prompt.title} style={styles.promptCard}>
      <View style={styles.promptHeader}>
        <View style={[styles.promptIcon, { backgroundColor: style.wash }]}>
          <Ionicons name={style.icon} size={19} color={style.tint} />
        </View>
        <View style={styles.promptHeaderText}>
          <Text style={styles.promptTitle}>{prompt.title}</Text>
          {prompt.reason ? <Text style={styles.promptReason}>{prompt.reason}</Text> : null}
        </View>
        {prompt.wantsPhoto ? <Badge label="Photo" tone="warning" icon="camera-outline" /> : null}
      </View>

      <Text style={styles.promptBody}>{prompt.body}</Text>

      <View style={styles.promptCta}>
        <Text style={[styles.promptCtaText, { color: style.tint }]}>
          {prompt.wantsPhoto ? 'Add a photo' : 'Share this'}
        </Text>
        <Ionicons name="arrow-forward" size={15} color={style.tint} />
        {rewardPoints ? (
          <View style={styles.promptReward}>
            <RewardChip points={rewardPoints} />
          </View>
        ) : null}
      </View>
    </Card>
  );
}

/**
 * Explore (Step 16) — proactive, location-aware discovery.
 *
 * Deliberately NOT a second question queue. Questions is the operational
 * backlog of knowledge the system has already decided it is missing; Explore
 * invites the guide to tell us things before we know to ask, and everything
 * shared here flows into the SAME knowledge system (see mobile/README.md).
 *
 * Every visible state maps to real backend/device state:
 *   - no synced profile   -> cannot fetch context at all, said plainly
 *   - no location yet     -> place-neutral prompts + a truthful nudge, never
 *                            a fabricated "you're near X"
 *   - context available   -> grounded prompts naming the real place/gaps
 *   - request failed      -> ErrorState with retry, never a silent empty deck
 */
export default function ExploreScreen({
  guide,
  place,
  onChangePlace,
  onStartContribution,
  onStartMemory,
  refreshKey,
}: Props) {
  const db = useSQLiteContext();
  const [context, setContext] = useState<GuideContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  // Reward values come from the BACKEND (see api/rewards.ts) -- this screen
  // never hardcodes what a contribution is worth. Null until loaded, in which
  // case cards simply show no reward rather than a guessed one.
  const [rewardConfig, setRewardConfig] = useState<RewardConfig | null>(null);
  // PRIMARY (category-driven) MISSING-only coverage gaps for the chosen
  // place -- STALE/PARTIALLY_STALE gaps deliberately stay off this screen,
  // same reasoning this screen already applies to hazard gaps and place
  // questions (see the comment on buildPrompts below): re-verifying
  // something already known is "verification work about one specific spot",
  // which belongs on the Questions tab, not here. A genuinely MISSING
  // category is closer to Explore's own purpose -- inviting the guide to
  // tell us something before we knew to ask.
  const [categoryGaps, setCategoryGaps] = useState<CategoryCoverage[]>([]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Local count first — it works with no network at all, so the "waiting to
      // sync" line stays truthful even when the context fetch below fails.
      const [pending, failed] = await Promise.all([
        countCapturesByStatus(db, guide.id, ['pending'], ['explore']),
        countCapturesByStatus(db, guide.id, ['failed'], ['explore']),
      ]);
      setPendingCount(pending + failed);

      if (!guide.serverGuideId) {
        setContext(null);
        return;
      }
      // Context only. Place questions and knowledge state both drive the
      // Questions tab now, so Explore no longer fetches either -- two network
      // calls that existed purely to render sections that have moved.
      setContext(await getGuideContext(guide.serverGuideId));

      // Loaded separately and never allowed to fail the screen: rewards are an
      // incentive layer, so a missing config means "show no points", not
      // "Explore is broken".
      try {
        setRewardConfig(await getRewardConfig());
      } catch {
        setRewardConfig(null);
      }

      // Same best-effort, never-fails-the-screen treatment: a chosen place's
      // category coverage is enrichment for the deck below, not a
      // precondition for it. No place chosen -> no fetch at all (never
      // fabricates coordinates or a Location).
      if (place) {
        try {
          const status = await getLocationKnowledgeStatus(place.id);
          setCategoryGaps(coverageGaps(status).filter((c) => c.state === 'missing'));
        } catch {
          setCategoryGaps([]);
        }
      } else {
        setCategoryGaps([]);
      }
    } catch (err) {
      const message =
        err instanceof ApiError || err instanceof NetworkError
          ? err.message
          : 'Could not load what we know about where you are.';
      setError(message);
    } finally {
      // Always released, on every path — the loading state can never outlive
      // the work it describes.
      setLoading(false);
      setLoaded(true);
    }
  }, [db, guide.id, guide.serverGuideId, place]);

  useEffect(() => {
    refresh();
  }, [refresh, refreshKey]);

  // Only a real pull gesture spins the RefreshControl — background loads (mount,
  // tab re-entry) show the inline "Checking where you are…" state instead.
  const { pulling, onPull } = usePullToRefresh(refresh);

  // Generic prompts ONLY. Two kinds of ask deliberately do not appear here:
  //
  //   place questions  -> Questions tab, "About This Place"
  //   knowledge gaps   -> Questions tab, "Still True?"
  //
  // Both are verification work about one specific spot, and Explore is the
  // contribution surface: open prompts a guide can act on anywhere. Passing
  // `null` for knowledge states is what keeps gap-derived prompts out (see
  // buildPrompts), and with no place questions competing for the space the
  // deck runs at its full length rather than trimmed.
  // Prompts still ground themselves in the backend context (coordinates,
  // recency) but name the CHOSEN place, so a card never says "Avasa Hotel"
  // when the guide picked the shop next door. Synthesising the shape
  // buildPrompts already expects keeps that function unchanged.
  const prompts = buildPrompts(
    context && place
      ? {
          ...context,
          nearestKnownPlace: {
            id: place.id,
            name: place.name,
            distanceMeters: place.distanceMeters,
          },
        }
      : context,
    null,
    false,
    categoryGaps
  );

  /** What an Explore contribution answering THIS prompt is currently worth.
   * A prompt asking for a photo is labelled with the media-inclusive total,
   * because that is genuinely what the guide earns if they do what the card
   * asks -- the base award plus the media bonus (see
   * backend/app/services/submissions.py). Any other prompt shows the base
   * award only; the bonus is still granted if they happen to attach media,
   * we just don't promise it up front for a card that didn't ask for it. */
  function rewardForPrompt(prompt: ExplorePrompt): number | null {
    if (!rewardConfig) return null;
    const base = rewardConfig.rules.find((r) => r.ruleKey === 'explore_contribution')?.points ?? 0;
    if (!prompt.wantsPhoto) return base || null;
    const bonus =
      rewardConfig.rules.find((r) => r.ruleKey === 'explore_contribution_media_bonus')?.points ?? 0;
    return base + bonus || null;
  }

  return (
    <Screen onRefresh={onPull} refreshing={pulling} footerSpace={8}>
      <View style={styles.header}>
        <Text style={styles.title}>Explore</Text>
        <Text style={styles.subtitle}>
          Tell us about where you are — before anyone thinks to ask.
        </Text>
      </View>

      {/* Location hero — states are mutually exclusive and all truthful. */}
      {!guide.serverGuideId ? (
        <Card style={styles.heroUnknown}>
          <View style={styles.heroRow}>
            <Ionicons name="cloud-offline-outline" size={20} color={colors.inkFaint} />
            <Text style={styles.heroUnknownTitle}>Profile not synced yet</Text>
          </View>
          <Text style={styles.heroUnknownBody}>
            You can still write and save discoveries now — they'll be sent once your profile
            syncs from the Home screen.
          </Text>
        </Card>
      ) : !place && context ? (
        // No chosen place: the guide skipped the picker because choosing was
        // impossible (offline, no permission, nowhere mapped). This is the
        // ORIGINAL hero, unchanged -- GPS's own answer, with no "Change"
        // affordance because there is nothing chosen to change.
        <View style={styles.hero}>
          <View style={styles.heroTopRow}>
            <Ionicons name="location" size={15} color={colors.marigold} />
            <Text style={styles.heroEyebrow}>AROUND YOU</Text>
          </View>
          <Text style={styles.heroPlace}>
            {context.nearestKnownPlace ? context.nearestKnownPlace.name : 'An unnamed spot'}
          </Text>
          <Text style={styles.heroMeta}>
            {context.nearestKnownPlace
              ? `about ${Math.round(context.nearestKnownPlace.distanceMeters)}m away · location ${describeAge(context.recordedAt)}`
              : `No known place nearby · location ${describeAge(context.recordedAt)}`}
          </Text>
        </View>
      ) : place ? (
        // The guide's OWN choice, not a GPS guess -- so this states it as
        // settled fact and offers the way to change it, rather than reporting
        // a distance to something they never picked.
        <Pressable
          onPress={onChangePlace}
          accessibilityRole="button"
          accessibilityLabel={`Contributing to ${place.name}. Tap to choose a different place.`}
          style={({ pressed }) => [styles.hero, pressed && styles.heroPressed]}
        >
          <View style={styles.heroTopRow}>
            <Ionicons name="location" size={15} color={colors.marigold} />
            <Text style={styles.heroEyebrow}>CONTRIBUTING TO</Text>
            <Text style={styles.heroChange}>Change</Text>
          </View>
          <Text style={styles.heroPlace}>{place.name}</Text>
          <Text style={styles.heroMeta}>
            {[
              describeCandidateKind(place),
              describeCandidateDistance(place),
              context ? `location ${describeAge(context.recordedAt)}` : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </Text>
        </Pressable>
      ) : loading && !loaded ? (
        <Card variant="flat" style={styles.heroLoading}>
          <Text style={styles.heroLoadingText}>Checking where you are…</Text>
        </Card>
      ) : (
        <Card style={styles.heroUnknown}>
          <View style={styles.heroRow}>
            <Ionicons name="navigate-circle-outline" size={20} color={colors.inkFaint} />
            <Text style={styles.heroUnknownTitle}>Location not captured yet</Text>
          </View>
          <Text style={styles.heroUnknownBody}>
            Capture a location on the Home screen and Explore can ask about the actual place
            you're standing in. Until then these prompts stay general — we won't guess where
            you are.
          </Text>
        </Card>
      )}

      {pendingCount > 0 ? (
        <View style={styles.pendingRow}>
          <Badge
            label={`${pendingCount} discovery${pendingCount === 1 ? '' : ' items'} waiting to send`}
            tone="info"
            icon="cloud-upload-outline"
          />
        </View>
      ) : null}

      {error ? (
        <View style={styles.errorWrap}>
          <ErrorState message={error} onRetry={refresh} retrying={loading} />
        </View>
      ) : null}

      {/* ── 1. GENERAL IDEAS ───────────────────────────────────────────────
          The device-built rotating deck: things worth reporting anywhere,
          which is exactly what makes them Explore's rather than Questions'.
          Anything tied to one specific place -- researched place questions,
          knowledge gaps -- lives on the Questions tab now, so this section
          never has to compete with a more urgent, more specific ask. */}
      {prompts.length > 0 ? (
        <>
          <SectionHeader title="General ideas" meta={context && place ? place.name : undefined} />
          <Text style={styles.sectionIntro}>
            Everyday things worth reporting from anywhere on your route.
          </Text>
          {prompts.map((prompt) => (
            <PromptCard
              key={prompt.id}
              prompt={prompt}
              rewardPoints={rewardForPrompt(prompt)}
              onPress={() => onStartContribution(prompt)}
            />
          ))}
        </>
      ) : loaded && !error ? (
        <View style={styles.emptyWrap}>
          <EmptyState
            icon="compass-outline"
            title="Nothing to suggest yet"
            message="You can still tell us anything you've noticed — the options below always work."
          />
        </View>
      ) : null}

      {/* ── 2. SHARE ANYTHING / SHARE A MEMORY ─────────────────────────────
          Always available and never rotating, so they sit at the floor of the
          screen rather than competing with the prompts above -- a guide who
          has read past every idea and still has something to say lands
          exactly here. */}
      <SectionHeader title="Share anything" />
      <Text style={styles.sectionIntro}>
        Nothing above fit? Tell us in your own words, or add something from another day.
      </Text>
      <Pressable
        onPress={() => onStartContribution(FREE_FORM_PROMPT)}
        accessibilityRole="button"
        accessibilityLabel="Share anything"
        style={({ pressed }) => [styles.freeForm, pressed && styles.freeFormPressed]}
      >
        <View style={styles.freeFormIcon}>
          <Ionicons name="create-outline" size={20} color={colors.paper} />
        </View>
        <View style={styles.freeFormText}>
          <Text style={styles.freeFormTitle}>Share anything</Text>
          <Text style={styles.freeFormBody}>
            Seen something we didn't think to ask about?
          </Text>
        </View>
        <Ionicons name="arrow-forward" size={18} color={colors.paper} />
      </Pressable>

      {/* Same visual treatment as "Share anything" on purpose — a memory is
          the same kind of proactive, no-prompt-needed contribution, just one
          that might be about a different time and place than right now (see
          MemoryContributeScreen for how location/date are figured out). */}
      <Pressable
        onPress={onStartMemory}
        accessibilityRole="button"
        accessibilityLabel="Share a memory"
        style={({ pressed }) => [styles.freeForm, pressed && styles.freeFormPressed]}
      >
        <View style={styles.freeFormIcon}>
          <Ionicons name="images-outline" size={20} color={colors.paper} />
        </View>
        <View style={styles.freeFormText}>
          <Text style={styles.freeFormTitle}>Share a memory</Text>
          <Text style={styles.freeFormBody}>An old photo, or a story from another trip</Text>
        </View>
        <Ionicons name="arrow-forward" size={18} color={colors.paper} />
      </Pressable>

      <Text style={styles.footnote}>
        Everything you share is saved on this device first and sent when you sync.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { marginBottom: spacing.md },
  title: { ...type.display, fontSize: 26, color: colors.ink },
  subtitle: { ...type.small, color: colors.inkFaint, marginTop: 4 },

  hero: {
    backgroundColor: colors.ink,
    borderRadius: radii.lg,
    padding: spacing.lg,
    marginBottom: spacing.sm,
    ...shadow.card,
  },
  heroPressed: { opacity: 0.85 },
  heroTopRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  heroEyebrow: { ...type.captionBold, color: colors.marigold, letterSpacing: 0.7 },
  heroChange: {
    ...type.captionBold,
    color: colors.marigold,
    marginLeft: 'auto',
    textDecorationLine: 'underline',
  },
  heroPlace: { ...type.title, color: colors.white, marginTop: spacing.xxs },
  heroMeta: { ...type.small, color: 'rgba(255,255,255,0.7)', marginTop: 2 },

  heroLoading: { marginBottom: spacing.sm },
  heroLoadingText: { ...type.small, color: colors.inkFaint },

  heroUnknown: { marginBottom: spacing.sm },
  heroRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  heroUnknownTitle: { ...type.subtitle, color: colors.ink },
  heroUnknownBody: { ...type.small, color: colors.inkSoft, marginTop: spacing.xs, lineHeight: 19 },

  pendingRow: { flexDirection: 'row', marginBottom: spacing.xs },
  errorWrap: { marginVertical: spacing.sm },
  emptyWrap: { marginTop: spacing.lg },
  // One line under each SectionHeader saying what that section IS. Explore
  // now carries three kinds of ask, and without this they look interchangeable.
  sectionIntro: {
    ...type.small,
    color: colors.inkFaint,
    marginTop: -spacing.xs,
    marginBottom: spacing.sm,
  },

  freeForm: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.marigoldDeep,
    borderRadius: radii.lg,
    padding: spacing.md,
    marginBottom: spacing.md,
    minHeight: 64,
    ...shadow.card,
  },
  freeFormPressed: { opacity: 0.9 },
  freeFormIcon: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: 'rgba(255,255,255,0.18)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  freeFormText: { flex: 1 },
  freeFormTitle: { ...type.subtitle, color: colors.paper },
  freeFormBody: { ...type.caption, color: 'rgba(250,244,233,0.82)', marginTop: 1 },

  promptCard: { marginBottom: spacing.sm },
  promptHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
  promptIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  promptHeaderText: { flex: 1 },
  promptTitle: { ...type.subtitle, color: colors.ink },
  promptReason: { ...type.caption, color: colors.inkFaint, marginTop: 1 },
  promptBody: { ...type.body, color: colors.inkSoft, marginTop: spacing.sm, lineHeight: 22 },
  promptCta: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: spacing.sm },
  promptCtaText: { ...type.smallBold },
  // Pushed to the trailing edge so the reward reads as a supporting detail
  // beside the action, never as the card's headline.
  promptReward: { marginLeft: 'auto' },

  footnote: {
    ...type.caption,
    color: colors.inkFaint,
    textAlign: 'center',
    marginTop: spacing.lg,
    lineHeight: 17,
  },
});
