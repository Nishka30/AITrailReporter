import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { ApiError, NetworkError } from '../api/client';
import {
  getGuideContext,
  getGuideKnowledgeState,
  type GuideContext,
  type KnowledgeTypeState,
} from '../api/guideContext';
import { Badge, Button, Card, EmptyState, ErrorState, Screen, SectionHeader } from '../components/ui';
import {
  FREE_FORM_PROMPT,
  buildPrompts,
  type ExplorePrompt,
} from '../explore/explorePrompts';
import { countCapturesByStatus } from '../repositories/captureRepository';
import { colors, radii, shadow, spacing, type } from '../theme/theme';
import type { LocalGuide } from '../types/models';

type Props = {
  guide: LocalGuide;
  onStartContribution: (prompt: ExplorePrompt) => void;
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

function PromptCard({ prompt, onPress }: { prompt: ExplorePrompt; onPress: () => void }) {
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
export default function ExploreScreen({ guide, onStartContribution, refreshKey }: Props) {
  const db = useSQLiteContext();
  const [context, setContext] = useState<GuideContext | null>(null);
  const [knowledgeStates, setKnowledgeStates] = useState<KnowledgeTypeState[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);

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
        setKnowledgeStates(null);
        return;
      }
      const [ctx, states] = await Promise.all([
        getGuideContext(guide.serverGuideId),
        getGuideKnowledgeState(guide.serverGuideId),
      ]);
      setContext(ctx);
      setKnowledgeStates(states);
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
  }, [db, guide.id, guide.serverGuideId]);

  useEffect(() => {
    refresh();
  }, [refresh, refreshKey]);

  const prompts = buildPrompts(context, knowledgeStates);
  const place = context?.nearestKnownPlace;

  return (
    <Screen onRefresh={refresh} refreshing={loading && loaded} footerSpace={8}>
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
      ) : context ? (
        <View style={styles.hero}>
          <View style={styles.heroTopRow}>
            <Ionicons name="location" size={15} color={colors.marigold} />
            <Text style={styles.heroEyebrow}>AROUND YOU</Text>
          </View>
          <Text style={styles.heroPlace}>{place ? place.name : 'An unnamed spot'}</Text>
          <Text style={styles.heroMeta}>
            {place
              ? `about ${Math.round(place.distanceMeters)}m away · location ${describeAge(context.recordedAt)}`
              : `No known place nearby · location ${describeAge(context.recordedAt)}`}
          </Text>
        </View>
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

      {/* Free-form path is permanent and always first — a guide must never have
          to wait for the right card to appear to report something. */}
      <SectionHeader title="In your own words" />
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

      {prompts.length > 0 ? (
        <>
          <SectionHeader
            title="Ideas for right here"
            meta={context && place ? place.name : undefined}
          />
          {prompts.map((prompt) => (
            <PromptCard
              key={prompt.id}
              prompt={prompt}
              onPress={() => onStartContribution(prompt)}
            />
          ))}
        </>
      ) : loaded && !error ? (
        <View style={styles.emptyWrap}>
          <EmptyState
            icon="compass-outline"
            title="No suggestions right now"
            message="You can still share anything you've noticed using the button above."
          />
        </View>
      ) : null}

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
  heroTopRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  heroEyebrow: { ...type.captionBold, color: colors.marigold, letterSpacing: 0.7 },
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

  footnote: {
    ...type.caption,
    color: colors.inkFaint,
    textAlign: 'center',
    marginTop: spacing.lg,
    lineHeight: 17,
  },
});
