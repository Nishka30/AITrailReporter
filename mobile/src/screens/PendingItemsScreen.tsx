import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { triggerTranscription, type TranscriptionResponse } from '../api/transcriptions';
import { triggerExtraction, type ExtractionResponse } from '../api/extractions';
import { ApiError, NetworkError } from '../api/client';
import { Badge, type BadgeTone, Button, Card, EmptyState, Screen, SectionHeader } from '../components/ui';
import { listCaptures } from '../repositories/captureRepository';
import { listLocations } from '../repositories/locationRepository';
import { colors, spacing, type } from '../theme/theme';
import type { LocalCapture, LocalGuide, LocalLocation, SyncStatus } from '../types/models';

type Props = {
  guide: LocalGuide;
  refreshKey: number;
};

function syncBadge(status: SyncStatus): { label: string; tone: BadgeTone; icon: keyof typeof Ionicons.glyphMap } {
  switch (status) {
    case 'pending':
      return { label: 'Waiting to send', tone: 'warning', icon: 'time-outline' };
    case 'uploading':
      return { label: 'Sending…', tone: 'info', icon: 'sync-outline' };
    case 'uploaded':
      return { label: 'Sent to server', tone: 'success', icon: 'checkmark-circle-outline' };
    case 'processing':
      return { label: 'Processing', tone: 'info', icon: 'sync-outline' };
    case 'synced':
      return { label: 'Synced', tone: 'success', icon: 'checkmark-circle-outline' };
    case 'failed':
      return { label: 'Send failed — will retry', tone: 'danger', icon: 'alert-circle-outline' };
    case 'dead_letter':
      return { label: 'Could not be sent', tone: 'danger', icon: 'close-circle-outline' };
    default:
      return { label: status, tone: 'neutral', icon: 'ellipse-outline' };
  }
}

// Failed items surface first within each section — progressive disclosure
// (Part I) without a second, duplicate "needs attention" list to keep in
// sync with the real one.
function byNeedsAttentionFirst<T extends { syncStatus: SyncStatus }>(items: T[]): T[] {
  return [...items].sort((a, b) => Number(b.syncStatus === 'failed') - Number(a.syncStatus === 'failed'));
}

function formatExtractionStatus(e: ExtractionResponse): { label: string; tone: BadgeTone } {
  switch (e.status) {
    case 'pending':
      return { label: 'Understanding pending', tone: 'neutral' };
    case 'processing':
      return { label: 'Reading…', tone: 'info' };
    case 'completed':
      return {
        label: `Understood — ${e.observations.length} detail${e.observations.length === 1 ? '' : 's'} found`,
        tone: 'success',
      };
    case 'failed':
      return { label: 'Could not read this', tone: 'danger' };
    default:
      return { label: e.status, tone: 'neutral' };
  }
}

// Explicit, manual, on-demand -- same discipline as transcription (Step 8):
// no polling, no auto-trigger, backend truth over UI guesswork. Tapping
// "Extract" both starts extraction (if nothing has run yet) and checks its
// current state (if something already has); the backend decides which. Shown
// only once source text actually exists on the server: a synced note, or a
// voice item whose transcription has completed (checked by the caller before
// rendering this).
function ExtractionBlock({ submissionId }: { submissionId: string }) {
  const [extraction, setExtraction] = useState<ExtractionResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);

  async function handleExtractPress() {
    if (checking) return;
    setChecking(true);
    setCheckError(null);
    try {
      const result = await triggerExtraction(submissionId);
      setExtraction(result);
    } catch (err) {
      const message =
        err instanceof ApiError || err instanceof NetworkError ? err.message : 'Could not check status.';
      setCheckError(message);
    } finally {
      setChecking(false);
    }
  }

  const status = extraction ? formatExtractionStatus(extraction) : null;

  return (
    <View style={styles.nestedBlock}>
      {status ? (
        <View style={styles.nestedBadgeRow}>
          <Badge label={status.label} tone={status.tone} />
        </View>
      ) : null}
      {extraction?.status === 'completed'
        ? extraction.observations.map((obs) => (
            <Text key={obs.id} style={styles.nestedDetailText}>
              • {obs.knowledgeType}: {JSON.stringify(obs.value)}
            </Text>
          ))
        : null}
      {extraction?.status === 'failed' && extraction.errorMessage ? (
        <Text style={styles.nestedErrorText}>{extraction.errorMessage}</Text>
      ) : null}
      {checkError ? <Text style={styles.nestedErrorText}>{checkError}</Text> : null}
      {extraction?.status !== 'completed' ? (
        <Button
          label={extraction ? 'Check again' : 'Understand this report'}
          onPress={handleExtractPress}
          loading={checking}
          variant="ghost"
          fullWidth={false}
        />
      ) : null}
    </View>
  );
}

function NoteItem({ item }: { item: LocalCapture }) {
  const badge = syncBadge(item.syncStatus);
  return (
    <Card style={styles.item}>
      <View style={styles.itemHeaderRow}>
        <Text style={styles.itemType}>Note</Text>
        <Text style={styles.itemDate}>{new Date(item.createdAt).toLocaleDateString()}</Text>
      </View>
      <Text style={styles.itemText} numberOfLines={4}>
        {item.textContent}
      </Text>
      <View style={styles.itemBadgeRow}>
        <Badge label={badge.label} tone={badge.tone} icon={badge.icon} />
      </View>
      {item.syncStatus === 'failed' && item.lastSyncError ? (
        <Text style={styles.nestedErrorText}>{item.lastSyncError}</Text>
      ) : null}

      {item.serverSubmissionId ? (
        <ExtractionBlock submissionId={item.serverSubmissionId} />
      ) : (
        <Text style={styles.itemMeta}>Send this note before it can be understood.</Text>
      )}
    </Card>
  );
}

function formatDuration(ms: number | null): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return 'duration unknown';
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function formatTranscriptionStatus(t: TranscriptionResponse): { label: string; tone: BadgeTone } {
  switch (t.status) {
    case 'pending':
      return { label: 'Listening pending', tone: 'neutral' };
    case 'processing':
      return { label: 'Listening…', tone: 'info' };
    case 'completed':
      return { label: 'Transcribed', tone: 'success' };
    case 'failed':
      return { label: 'Could not transcribe', tone: 'danger' };
    default:
      return { label: t.status, tone: 'neutral' };
  }
}

// Playback is intentionally out of scope (record -> save -> sync -> server
// reference only) -- this item shows metadata only, never a fake "play"
// affordance. Transcription is a manual, on-demand fetch, same discipline as
// extraction -- see ExtractionBlock above.
function VoiceItem({ item }: { item: LocalCapture }) {
  const [transcription, setTranscription] = useState<TranscriptionResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const badge = syncBadge(item.syncStatus);

  async function handleTranscribePress() {
    if (!item.serverSubmissionId || checking) return;
    setChecking(true);
    setCheckError(null);
    try {
      const result = await triggerTranscription(item.serverSubmissionId);
      setTranscription(result);
    } catch (err) {
      const message =
        err instanceof ApiError || err instanceof NetworkError ? err.message : 'Could not check status.';
      setCheckError(message);
    } finally {
      setChecking(false);
    }
  }

  const transcriptionStatus = transcription ? formatTranscriptionStatus(transcription) : null;

  return (
    <Card style={styles.item}>
      <View style={styles.itemHeaderRow}>
        <View style={styles.itemTypeRow}>
          <Ionicons name="mic-outline" size={13} color={colors.inkFaint} />
          <Text style={styles.itemType}>Voice</Text>
        </View>
        <Text style={styles.itemDate}>{new Date(item.createdAt).toLocaleDateString()}</Text>
      </View>
      <Text style={styles.itemText}>{formatDuration(item.audioDurationMillis)}</Text>
      <View style={styles.itemBadgeRow}>
        <Badge label={badge.label} tone={badge.tone} icon={badge.icon} />
      </View>
      {item.syncStatus === 'failed' && item.lastSyncError ? (
        <Text style={styles.nestedErrorText}>{item.lastSyncError}</Text>
      ) : null}

      {item.serverSubmissionId ? (
        <View style={styles.nestedBlock}>
          {transcriptionStatus ? (
            <View style={styles.nestedBadgeRow}>
              <Badge label={transcriptionStatus.label} tone={transcriptionStatus.tone} />
            </View>
          ) : null}
          {transcription?.status === 'completed' && transcription.transcript ? (
            <Text style={styles.nestedQuoteText}>"{transcription.transcript}"</Text>
          ) : null}
          {transcription?.status === 'failed' && transcription.errorMessage ? (
            <Text style={styles.nestedErrorText}>{transcription.errorMessage}</Text>
          ) : null}
          {checkError ? <Text style={styles.nestedErrorText}>{checkError}</Text> : null}

          {transcription?.status !== 'completed' ? (
            <Button
              label={transcription ? 'Check again' : 'Listen to this recording'}
              onPress={handleTranscribePress}
              loading={checking}
              variant="ghost"
              fullWidth={false}
            />
          ) : (
            // Extraction only makes sense once a transcript actually exists.
            <ExtractionBlock submissionId={item.serverSubmissionId} />
          )}
        </View>
      ) : (
        <Text style={styles.itemMeta}>Send this recording before it can be transcribed.</Text>
      )}
    </Card>
  );
}

function LocationItem({ item }: { item: LocalLocation }) {
  const badge = syncBadge(item.syncStatus);
  return (
    <Card style={styles.item}>
      <View style={styles.itemHeaderRow}>
        <View style={styles.itemTypeRow}>
          <Ionicons name="location-outline" size={13} color={colors.inkFaint} />
          <Text style={styles.itemType}>Location</Text>
        </View>
        <Text style={styles.itemDate}>{new Date(item.recordedAt).toLocaleDateString()}</Text>
      </View>
      <Text style={styles.itemText}>
        {item.latitude.toFixed(5)}, {item.longitude.toFixed(5)}
        {item.accuracyMeters != null ? `  ·  ±${Math.round(item.accuracyMeters)}m` : ''}
      </Text>
      <View style={styles.itemBadgeRow}>
        <Badge label={badge.label} tone={badge.tone} icon={badge.icon} />
      </View>
      {item.syncStatus === 'failed' && item.lastSyncError ? (
        <Text style={styles.nestedErrorText}>{item.lastSyncError}</Text>
      ) : null}
    </Card>
  );
}

export default function PendingItemsScreen({ guide, refreshKey }: Props) {
  const db = useSQLiteContext();
  const [captures, setCaptures] = useState<LocalCapture[]>([]);
  const [locations, setLocations] = useState<LocalLocation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [captureRows, locationRows] = await Promise.all([listCaptures(db, guide.id), listLocations(db, guide.id)]);
      setCaptures(captureRows);
      setLocations(locationRows);
      setError(null);
    } catch (err) {
      console.error('[PendingItemsScreen] Failed to load local data:', err);
      setError('Could not read local data.');
    } finally {
      setLoading(false);
    }
  }, [db, guide.id]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const notes = byNeedsAttentionFirst(captures.filter((c) => c.captureType === 'note'));
  const voiceCaptures = byNeedsAttentionFirst(captures.filter((c) => c.captureType === 'voice'));
  const sortedLocations = byNeedsAttentionFirst(locations);
  const isEmpty = notes.length === 0 && voiceCaptures.length === 0 && sortedLocations.length === 0;

  return (
    <Screen onRefresh={load} refreshing={loading}>
      <View style={styles.header}>
        <Text style={styles.title}>Activity</Text>
        <Text style={styles.subtitle}>Everything saved on this device — status shows what's actually reached the server.</Text>
      </View>

      {error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : isEmpty && !loading ? (
        <EmptyState
          icon="file-tray-outline"
          title="Nothing captured yet"
          message="Notes, voice updates, and locations you save will show up here."
        />
      ) : (
        <>
          <SectionHeader title="Notes" meta={String(notes.length)} />
          {notes.length === 0 ? (
            <Text style={styles.emptyText}>No notes yet.</Text>
          ) : (
            notes.map((item) => <NoteItem key={item.id} item={item} />)
          )}

          <SectionHeader title="Voice updates" meta={String(voiceCaptures.length)} />
          {voiceCaptures.length === 0 ? (
            <Text style={styles.emptyText}>No voice updates yet.</Text>
          ) : (
            voiceCaptures.map((item) => <VoiceItem key={item.id} item={item} />)
          )}

          <SectionHeader title="Locations" meta={String(sortedLocations.length)} />
          {sortedLocations.length === 0 ? (
            <Text style={styles.emptyText}>No locations captured yet.</Text>
          ) : (
            sortedLocations.map((item) => <LocationItem key={item.id} item={item} />)
          )}
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { marginBottom: spacing.sm },
  title: { ...type.display, fontSize: 26, color: colors.ink },
  subtitle: { ...type.small, color: colors.inkFaint, marginTop: 4, lineHeight: 18 },
  emptyText: { ...type.small, color: colors.inkFaint, marginBottom: spacing.sm },
  errorText: { ...type.small, color: colors.fix, marginTop: spacing.xl, textAlign: 'center' },
  item: { marginBottom: spacing.sm },
  itemHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.xs },
  itemTypeRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  itemType: { ...type.captionBold, color: colors.inkFaint, letterSpacing: 0.5, textTransform: 'uppercase' },
  itemDate: { ...type.caption, color: colors.inkFaint },
  itemText: { ...type.body, color: colors.ink, marginBottom: spacing.xs },
  itemBadgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: 2 },
  itemMeta: { ...type.caption, color: colors.inkFaint, marginTop: spacing.sm, fontStyle: 'italic' },
  nestedBlock: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    gap: spacing.xs,
    alignItems: 'flex-start',
  },
  nestedBadgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  nestedQuoteText: { ...type.small, color: colors.ink, fontStyle: 'italic' },
  nestedDetailText: { ...type.small, color: colors.ink },
  nestedErrorText: { ...type.caption, color: colors.fix },
});
