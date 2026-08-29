import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { listAssignedQuestions } from '../api/questions';
import VoiceRecorderCard from '../components/VoiceRecorderCard';
import { Avatar, Badge, Button, Card, QuickActionTile, Screen, SectionHeader } from '../components/ui';
import { captureCurrentLocation } from '../location/locationService';
import { countCapturesByStatus } from '../repositories/captureRepository';
import { countLocationsByStatus, createLocation, getLatestLocation } from '../repositories/locationRepository';
import { syncAll, type SyncResult } from '../sync/syncService';
import { colors, spacing, type } from '../theme/theme';
import type { LocalGuide, LocalLocation } from '../types/models';

type Props = {
  guide: LocalGuide;
  onCreateNote: () => void;
  onViewQuestions: () => void;
  onViewExplore: () => void;
  onViewActivity: () => void;
  /** Opens the Profile screen (Step 17) — wired to the header avatar. */
  onOpenProfile: () => void;
  refreshKey: number;
};

function formatCoordinate(value: number): string {
  return value.toFixed(5);
}

/** Everything Home needs about "is stuff waiting to go out?", computed
 * purely from local SQLite — no network. */
function useSyncSnapshot(guide: LocalGuide, refreshKey: number) {
  const db = useSQLiteContext();
  const [waiting, setWaiting] = useState<number | null>(null);
  const [failed, setFailed] = useState<number | null>(null);
  const [uploaded, setUploaded] = useState<number | null>(null);
  const [latestLocation, setLatestLocation] = useState<LocalLocation | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Guards against two refresh() calls overlapping on the same SQLite
  // connection (e.g. a rapid double tab-switch bumping refreshKey twice in a
  // row) — expo-sqlite can throw "shared object already released" when two
  // in-flight statements race, so a second call while one is still running
  // is dropped rather than started.
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      // Sequential, not Promise.all: overlapping async calls into the same
      // connection are what triggers the native statement race above.
      const captureWaiting = await countCapturesByStatus(db, guide.id, ['pending']);
      const captureFailed = await countCapturesByStatus(db, guide.id, ['failed']);
      const captureUploaded = await countCapturesByStatus(db, guide.id, ['uploaded']);
      const locationWaiting = await countLocationsByStatus(db, guide.id, ['pending']);
      const locationFailed = await countLocationsByStatus(db, guide.id, ['failed']);
      const loc = await getLatestLocation(db, guide.id);
      setWaiting(captureWaiting + locationWaiting);
      setFailed(captureFailed + locationFailed);
      setUploaded(captureUploaded);
      setLatestLocation(loc);
      setError(null);
    } catch (err) {
      console.error('[HomeScreen] Failed to read local sync counts:', err);
      setError('Could not read local data.');
    } finally {
      inFlight.current = false;
    }
  }, [db, guide.id]);

  useEffect(() => {
    refresh();
  }, [refresh, refreshKey]);

  return { waiting, failed, uploaded, latestLocation, error, refresh };
}

/** How many currently-assigned questions still need the guide's input — a
 * single, cheap, honest fetch of the real server truth (assignment.status
 * !== 'completed'). Not shown at all until it resolves — never a fabricated
 * placeholder count.
 *
 * Step 16: Home no longer RENDERS the question queue (that moved wholly to the
 * Questions tab); this count now feeds only a compact shortcut row. The fetch
 * is kept here rather than lifted to RootNavigator deliberately — the badge
 * RootNavigator holds is populated by QuestionsScreen, so it is null until
 * that tab has been visited at least once, and Home must be truthful on a cold
 * start. Only one tab is mounted at a time, so this never races or duplicates
 * a simultaneous request. */
function useAttentionQuestionCount(guide: LocalGuide, refreshKey: number) {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    if (!guide.serverGuideId) {
      setCount(null);
      return;
    }
    let cancelled = false;
    listAssignedQuestions(guide.serverGuideId)
      .then((questions) => {
        if (cancelled) return;
        const needsAttention = questions.filter(
          (q) => q.assignment && q.assignment.status !== 'completed'
        ).length;
        setCount(needsAttention);
      })
      .catch((err) => {
        console.error('[HomeScreen] Failed to load question count:', err);
        if (!cancelled) setCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [guide.serverGuideId, refreshKey]);

  return count;
}

export default function HomeScreen({
  guide,
  onCreateNote,
  onViewQuestions,
  onViewExplore,
  onViewActivity,
  onOpenProfile,
  refreshKey,
}: Props) {
  const db = useSQLiteContext();
  const sync = useSyncSnapshot(guide, refreshKey);
  const attentionQuestions = useAttentionQuestionCount(guide, refreshKey);

  const [syncing, setSyncing] = useState(false);
  const [lastSyncResult, setLastSyncResult] = useState<SyncResult | null>(null);
  const [capturingLocation, setCapturingLocation] = useState(false);
  const [locationMessage, setLocationMessage] = useState<string | null>(null);

  async function handleSyncNow() {
    if (syncing) return;
    setSyncing(true);
    try {
      const result = await syncAll(db);
      setLastSyncResult(result);
      await sync.refresh();
    } catch (err) {
      console.error('[HomeScreen] Sync failed unexpectedly:', err);
      setLastSyncResult({
        ranAt: new Date().toISOString(),
        guideSynced: false,
        guideError: 'Unexpected error',
        profileError: null,
        notes: { attempted: 0, uploaded: 0, failed: 0, outcomes: [] },
        voice: { attempted: 0, uploaded: 0, failed: 0, outcomes: [] },
        explore: { attempted: 0, uploaded: 0, failed: 0, outcomes: [] },
        locations: { attempted: 0, uploaded: 0, failed: 0, outcomes: [] },
        answers: { attempted: 0, uploaded: 0, failed: 0, outcomes: [] },
        message: 'Sync failed unexpectedly. Your local data is safe and unchanged.',
      });
    } finally {
      setSyncing(false);
    }
  }

  async function handleCaptureLocation() {
    if (capturingLocation) return;
    setCapturingLocation(true);
    setLocationMessage(null);
    try {
      const result = await captureCurrentLocation();
      if (result.status === 'success') {
        await createLocation(
          db,
          guide.id,
          result.location.latitude,
          result.location.longitude,
          result.location.accuracyMeters,
          result.location.recordedAt
        );
        setLocationMessage('Saved on this device — not yet sent to the server.');
        await sync.refresh();
      } else if (result.status === 'permission-denied') {
        setLocationMessage(
          result.canAskAgain
            ? 'Location permission is required. Please allow it and try again.'
            : 'Location permission was denied. Enable it for this app in your device settings.'
        );
      } else {
        setLocationMessage(result.message);
      }
    } catch (err) {
      console.error('[HomeScreen] Failed to capture location:', err);
      setLocationMessage('Could not capture location. Please try again.');
    } finally {
      setCapturingLocation(false);
    }
  }

  const hasWaiting = (sync.waiting ?? 0) + (sync.failed ?? 0) > 0;

  /** One truthful description of the last sync, shared by BOTH "Sync now"
   * buttons so they can never report different things. A guide-level failure
   * takes precedence: if the profile could not be resolved, nothing else was
   * attempted, and saying "nothing to sync" there would be a lie. */
  const syncMessage = lastSyncResult
    ? lastSyncResult.guideError
      ? `Sync could not run: ${lastSyncResult.guideError}`
      : lastSyncResult.message
    : null;

  return (
    <Screen footerSpace={8}>
      {/* The avatar is the entry point to the Profile screen (Step 17). It
          shows the guide's photo when they have set one and their initial
          otherwise — both handled by the shared Avatar component, so the header
          can never disagree with the Profile screen about how the guide is
          represented. */}
      <View style={styles.greetingRow}>
        <Avatar
          name={guide.name}
          photoUri={guide.localPhotoUri}
          size={52}
          onPress={onOpenProfile}
          accessibilityLabel="Open your profile"
          style={styles.avatarWrap}
        />
        <Pressable
          onPress={onOpenProfile}
          accessibilityRole="button"
          accessibilityLabel="Open your profile"
          style={({ pressed }) => [styles.greetingTextWrap, pressed && styles.greetingPressed]}
        >
          <Text style={styles.greeting}>Namaste, {guide.name}</Text>
          <Text style={styles.greetingSubtitle}>Offline-ready — everything saves on your device first</Text>
        </Pressable>
      </View>

      {/* Step 16: Home is a calm dashboard about THIS DEVICE's state — is
          anything waiting to go out? The operational question queue no longer
          lives here at all; it belongs to the Questions tab, and is surfaced
          below only as a compact shortcut. Derived from real local data only,
          never a fixed/generic message. */}
      {hasWaiting ? (
        <Card style={styles.heroCardMuted}>
          <Text style={styles.heroEyebrowMuted}>WAITING TO SEND</Text>
          <Text style={styles.heroTitleMuted}>
            {(sync.waiting ?? 0) + (sync.failed ?? 0)} item{(sync.waiting ?? 0) + (sync.failed ?? 0) === 1 ? '' : 's'} saved on this device
          </Text>
          <Text style={styles.heroSubtitleMuted}>Nothing is lost — send them whenever you have a connection.</Text>
          <View style={styles.heroButtonWrap}>
            <Button
              label={syncing ? 'Syncing…' : 'Sync now'}
              onPress={handleSyncNow}
              loading={syncing}
              fullWidth={false}
            />
          </View>
          {/* Both "Sync now" buttons run the SAME handler, so they must also
              report the same outcome. Without this, tapping the button up here
              and having the sync fail looked like nothing happened at all —
              the only result text lived in the Sync card far below, which the
              guide may never scroll to. */}
          {syncMessage ? <Text style={styles.heroResultText}>{syncMessage}</Text> : null}
        </Card>
      ) : (
        <Card style={styles.heroCardCalm}>
          <View style={styles.heroCalmRow}>
            <Ionicons name="checkmark-circle" size={22} color={colors.ok} />
            <Text style={styles.heroCalmTitle}>Everything is sent</Text>
          </View>
          <Text style={styles.heroSubtitleMuted}>
            Nothing is waiting on this device right now.
          </Text>
        </Card>
      )}

      {/* Compact navigation affordances — a truthful count and a way through,
          NOT a second copy of either queue. `attentionQuestions === null` means
          the count hasn't resolved (or couldn't be fetched); the row still
          navigates, it just doesn't claim a number it doesn't have. */}
      <View style={styles.shortcutRow}>
        <Card
          onPress={onViewExplore}
          accessibilityLabel="Open Explore"
          style={styles.shortcut}
        >
          <View style={[styles.shortcutIcon, { backgroundColor: colors.marigoldSoft }]}>
            <Ionicons name="compass-outline" size={19} color={colors.marigoldDeep} />
          </View>
          <Text style={styles.shortcutTitle}>Explore</Text>
          <Text style={styles.shortcutMeta}>Share what's around you</Text>
        </Card>

        <Card
          onPress={onViewQuestions}
          accessibilityLabel={
            attentionQuestions && attentionQuestions > 0
              ? `Open Questions, ${attentionQuestions} waiting`
              : 'Open Questions'
          }
          style={styles.shortcut}
        >
          <View style={styles.shortcutIconRow}>
            <View style={[styles.shortcutIcon, { backgroundColor: colors.infoSoft }]}>
              <Ionicons name="chatbubble-ellipses-outline" size={19} color={colors.info} />
            </View>
            {attentionQuestions !== null && attentionQuestions > 0 ? (
              <View style={styles.shortcutCount}>
                <Text style={styles.shortcutCountText}>{attentionQuestions}</Text>
              </View>
            ) : null}
          </View>
          <Text style={styles.shortcutTitle}>Questions</Text>
          <Text style={styles.shortcutMeta}>
            {attentionQuestions === null
              ? 'Asked by the server'
              : attentionQuestions === 0
                ? 'None waiting'
                : `${attentionQuestions} waiting for you`}
          </Text>
        </Card>
      </View>

      <SectionHeader title="Record an update" />
      <View style={styles.quickActionsRow}>
        <QuickActionTile icon="document-text-outline" label="Add note" onPress={onCreateNote} />
        <QuickActionTile
          icon="location-outline"
          label="Capture location"
          onPress={handleCaptureLocation}
          disabled={capturingLocation}
        />
      </View>

      <View style={styles.voiceCardWrap}>
        <VoiceRecorderCard guide={guide} onSaved={sync.refresh} />
      </View>

      {locationMessage ? (
        <Card variant="flat" style={styles.locationMessageCard}>
          <Text style={styles.locationMessageText}>{locationMessage}</Text>
        </Card>
      ) : null}

      {sync.latestLocation ? (
        <Card variant="flat" style={styles.locationCard}>
          <View style={styles.locationHeaderRow}>
            <Ionicons name="location" size={16} color={colors.inkFaint} />
            <Text style={styles.locationLabel}>Last known location</Text>
          </View>
          <Text style={styles.locationCoords}>
            {formatCoordinate(sync.latestLocation.latitude)}, {formatCoordinate(sync.latestLocation.longitude)}
          </Text>
          <Text style={styles.locationMeta}>
            {new Date(sync.latestLocation.recordedAt).toLocaleString()}
            {sync.latestLocation.accuracyMeters != null ? `  ·  ±${Math.round(sync.latestLocation.accuracyMeters)}m` : ''}
          </Text>
        </Card>
      ) : null}

      <SectionHeader title="Sync" />
      <Card>
        <View style={styles.syncBadgeRow}>
          {sync.waiting !== null && sync.waiting > 0 ? (
            <Badge label={`${sync.waiting} waiting`} tone="warning" icon="time-outline" />
          ) : null}
          {sync.failed !== null && sync.failed > 0 ? (
            <Badge label={`${sync.failed} failed`} tone="danger" icon="alert-circle-outline" />
          ) : null}
          {sync.uploaded !== null && sync.uploaded > 0 ? (
            <Badge label={`${sync.uploaded} sent`} tone="success" icon="checkmark-circle-outline" />
          ) : null}
          {!hasWaiting && (sync.uploaded ?? 0) === 0 ? (
            <Badge label="Nothing captured yet" tone="neutral" />
          ) : null}
        </View>

        <Text style={styles.syncHint}>
          "Sent" means the server has received it — not that it has been processed yet.
        </Text>

        <View style={styles.syncButtonWrap}>
          <Button label={syncing ? 'Syncing…' : 'Sync now'} onPress={handleSyncNow} loading={syncing} variant="secondary" />
        </View>

        {syncMessage ? <Text style={styles.syncResultText}>{syncMessage}</Text> : null}
      </Card>

      <SectionHeader title="More" />
      <Card onPress={onViewActivity} accessibilityLabel="View activity">
        <View style={styles.linkRow}>
          <View style={styles.linkRowText}>
            <Text style={styles.linkRowTitle}>Activity</Text>
            <Text style={styles.linkRowSubtitle}>Notes, voice updates, and locations saved on this device</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.inkFaint} />
        </View>
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  greetingRow: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.lg },
  avatarWrap: { marginRight: spacing.sm },
  greetingTextWrap: { flex: 1 },
  greetingPressed: { opacity: 0.7 },
  greeting: { ...type.display, fontSize: 24, lineHeight: 29, color: colors.ink },
  greetingSubtitle: { ...type.small, color: colors.inkFaint, marginTop: 2 },

  heroButtonWrap: { marginTop: spacing.md },
  heroResultText: { ...type.small, color: colors.inkSoft, marginTop: spacing.sm, lineHeight: 19 },

  shortcutRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.xs },
  shortcut: { flex: 1 },
  shortcutIconRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  shortcutIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  shortcutCount: {
    minWidth: 24,
    height: 24,
    borderRadius: 12,
    paddingHorizontal: 6,
    backgroundColor: colors.ink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  shortcutCountText: { ...type.captionBold, color: colors.marigoldSoft },
  shortcutTitle: { ...type.subtitle, color: colors.ink, marginTop: spacing.xs },
  shortcutMeta: { ...type.caption, color: colors.inkFaint, marginTop: 1 },

  heroCardMuted: { backgroundColor: colors.marigoldSoft, marginBottom: spacing.sm },
  heroEyebrowMuted: { ...type.captionBold, color: colors.marigoldDeep, letterSpacing: 0.6 },
  heroTitleMuted: { ...type.title, color: colors.ink, marginTop: spacing.xxs },
  heroSubtitleMuted: { ...type.small, color: colors.inkSoft, marginTop: spacing.xxs },

  heroCardCalm: { marginBottom: spacing.sm },
  heroCalmRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  heroCalmTitle: { ...type.subtitle, color: colors.ink },

  quickActionsRow: { flexDirection: 'row', gap: spacing.sm },
  voiceCardWrap: { marginTop: spacing.sm },

  locationMessageCard: { marginTop: spacing.sm },
  locationMessageText: { ...type.small, color: colors.inkSoft },

  locationCard: { marginTop: spacing.sm },
  locationHeaderRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 },
  locationLabel: { ...type.captionBold, color: colors.inkFaint, letterSpacing: 0.3 },
  locationCoords: { ...type.bodyBold, color: colors.ink },
  locationMeta: { ...type.caption, color: colors.inkFaint, marginTop: 2 },

  syncBadgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm },
  syncHint: { ...type.caption, color: colors.inkFaint, marginBottom: spacing.md },
  syncButtonWrap: { marginBottom: spacing.xs },
  syncResultText: { ...type.small, color: colors.inkSoft, marginTop: spacing.sm, lineHeight: 19 },

  linkRow: { flexDirection: 'row', alignItems: 'center' },
  linkRowText: { flex: 1 },
  linkRowTitle: { ...type.bodyBold, color: colors.ink },
  linkRowSubtitle: { ...type.small, color: colors.inkFaint, marginTop: 2 },
});
