import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { listAssignedQuestions } from '../api/questions';
import VoiceRecorderCard from '../components/VoiceRecorderCard';
import { Badge, Button, Card, QuickActionTile, Screen, SectionHeader } from '../components/ui';
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
  onViewActivity: () => void;
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

  const refresh = useCallback(async () => {
    try {
      const [captureWaiting, captureFailed, captureUploaded, locationWaiting, locationFailed, loc] =
        await Promise.all([
          countCapturesByStatus(db, guide.id, ['pending']),
          countCapturesByStatus(db, guide.id, ['failed']),
          countCapturesByStatus(db, guide.id, ['uploaded']),
          countLocationsByStatus(db, guide.id, ['pending']),
          countLocationsByStatus(db, guide.id, ['failed']),
          getLatestLocation(db, guide.id),
        ]);
      setWaiting(captureWaiting + locationWaiting);
      setFailed(captureFailed + locationFailed);
      setUploaded(captureUploaded);
      setLatestLocation(loc);
      setError(null);
    } catch (err) {
      console.error('[HomeScreen] Failed to read local sync counts:', err);
      setError('Could not read local data.');
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
 * placeholder count. */
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

export default function HomeScreen({ guide, onCreateNote, onViewQuestions, onViewActivity, refreshKey }: Props) {
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
        notes: { attempted: 0, uploaded: 0, failed: 0, outcomes: [] },
        voice: { attempted: 0, uploaded: 0, failed: 0, outcomes: [] },
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

  return (
    <Screen footerSpace={8}>
      <View style={styles.greetingRow}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{guide.name.trim().slice(0, 1).toUpperCase() || '?'}</Text>
        </View>
        <View style={styles.greetingTextWrap}>
          <Text style={styles.greeting}>Namaste, {guide.name}</Text>
          <Text style={styles.greetingSubtitle}>Offline-ready — everything saves on your device first</Text>
        </View>
      </View>

      {/* Adaptive hero: the single most useful next action, derived from
          real data only — never a fixed/generic message. */}
      {attentionQuestions !== null && attentionQuestions > 0 ? (
        <Card style={styles.heroCard} onPress={onViewQuestions} accessibilityLabel="Answer assigned questions">
          <Text style={styles.heroEyebrow}>NEEDS YOUR INPUT</Text>
          <Text style={styles.heroTitle}>
            {attentionQuestions} question{attentionQuestions === 1 ? '' : 's'} for you
          </Text>
          <Text style={styles.heroSubtitle}>
            The server would like a quick report from you on your current area.
          </Text>
          <View style={styles.heroButtonWrap}>
            <Button label="Answer now" onPress={onViewQuestions} fullWidth={false} />
          </View>
        </Card>
      ) : hasWaiting ? (
        <Card style={styles.heroCardMuted}>
          <Text style={styles.heroEyebrowMuted}>WAITING TO SEND</Text>
          <Text style={styles.heroTitleMuted}>
            {(sync.waiting ?? 0) + (sync.failed ?? 0)} item{(sync.waiting ?? 0) + (sync.failed ?? 0) === 1 ? '' : 's'} saved on this device
          </Text>
          <Text style={styles.heroSubtitleMuted}>Nothing is lost — send them whenever you have a connection.</Text>
          <View style={styles.heroButtonWrap}>
            <Button label="Sync now" onPress={handleSyncNow} loading={syncing} fullWidth={false} />
          </View>
        </Card>
      ) : (
        <Card style={styles.heroCardCalm}>
          <View style={styles.heroCalmRow}>
            <Ionicons name="checkmark-circle" size={22} color={colors.ok} />
            <Text style={styles.heroCalmTitle}>You're all caught up</Text>
          </View>
          <Text style={styles.heroSubtitleMuted}>No pending questions or unsent reports right now.</Text>
        </Card>
      )}

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

        {lastSyncResult ? (
          <Text style={styles.syncResultText}>
            {lastSyncResult.guideError ? `Sync could not run: ${lastSyncResult.guideError}` : lastSyncResult.message}
          </Text>
        ) : null}
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
  avatar: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: colors.ink,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
  },
  avatarText: { ...type.title, color: colors.marigoldSoft },
  greetingTextWrap: { flex: 1 },
  greeting: { ...type.display, fontSize: 24, lineHeight: 29, color: colors.ink },
  greetingSubtitle: { ...type.small, color: colors.inkFaint, marginTop: 2 },

  heroCard: { backgroundColor: colors.ink, marginBottom: spacing.sm },
  heroEyebrow: { ...type.captionBold, color: colors.marigold, letterSpacing: 0.6 },
  heroTitle: { ...type.title, color: colors.white, marginTop: spacing.xxs },
  heroSubtitle: { ...type.small, color: 'rgba(255,255,255,0.75)', marginTop: spacing.xxs },
  heroButtonWrap: { marginTop: spacing.md },

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
