import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { triggerTranscription, type TranscriptionResponse } from '../api/transcriptions';
import { triggerExtraction, type ExtractionResponse } from '../api/extractions';
import { ApiError, NetworkError } from '../api/client';
import { formatDurationOrUnknown } from '../audio/duration';
import { usePullToRefresh } from '../hooks/usePullToRefresh';
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

/**
 * An Explore discovery contribution (Step 16). Same truthful sync/extraction
 * reporting as NoteItem — it IS a submission and goes through the identical
 * extraction pipeline — plus two Explore-specific facts: which prompt it
 * answered (local-only provenance) and whether a photo is attached.
 *
 * The photo line reports the LOCAL attachment honestly: once the capture is
 * uploaded the photo went with it, but before that it is still only on this
 * device. It never claims the photo was understood — this step does no image
 * analysis, and the extraction block below reflects the TEXT only.
 */
function ExploreItem({ item }: { item: LocalCapture }) {
  const badge = syncBadge(item.syncStatus);
  const uploaded = item.syncStatus === 'uploaded';
  const hasVoice = Boolean(item.localAudioUri);
  const hasText = Boolean(item.textContent?.trim());

  return (
    <Card style={styles.item}>
      <View style={styles.itemHeaderRow}>
        <View style={styles.itemTypeRow}>
          <Ionicons name="compass-outline" size={13} color={colors.inkFaint} />
          <Text style={styles.itemType}>Discovery</Text>
        </View>
        <Text style={styles.itemDate}>{new Date(item.createdAt).toLocaleDateString()}</Text>
      </View>

      {item.explorePromptTitle ? (
        <Text style={styles.itemMetaTop}>In response to: {item.explorePromptTitle}</Text>
      ) : null}

      {/* A voice-only discovery genuinely has no text to show. Saying so is
          more honest than rendering an empty line that looks like a bug. */}
      {hasText ? (
        <Text style={styles.itemText} numberOfLines={4}>
          {item.textContent}
        </Text>
      ) : (
        <Text style={styles.itemTextMuted}>
          Spoken discovery · {formatDurationOrUnknown(item.audioDurationMillis)}
        </Text>
      )}

      <View style={styles.itemBadgeRow}>
        <Badge label={badge.label} tone={badge.tone} icon={badge.icon} />
        {hasVoice && hasText ? (
          <Badge
            label={uploaded ? 'Voice sent' : 'Voice attached'}
            tone={uploaded ? 'success' : 'info'}
            icon="mic-outline"
          />
        ) : null}
        {item.localPhotoUri ? (
          <Badge
            label={uploaded ? 'Photo sent' : 'Photo attached'}
            tone={uploaded ? 'success' : 'info'}
            icon="image-outline"
          />
        ) : null}
      </View>

      {item.syncStatus === 'failed' && item.lastSyncError ? (
        <Text style={styles.nestedErrorText}>{item.lastSyncError}</Text>
      ) : null}

      {item.serverSubmissionId ? (
        <View style={styles.nestedBlock}>
          {hasText ? (
            <>
              {/* Text is the source for extraction, so it can be understood
                  straight away — exactly as before Step 17. An attached voice
                  note can still be transcribed separately, which is why both
                  controls appear for a text+voice discovery. */}
              <ExtractionBlock submissionId={item.serverSubmissionId} />
              {hasVoice ? (
                <View style={styles.nestedDivider}>
                  <TranscriptionBlock
                    submissionId={item.serverSubmissionId}
                    startLabel="Transcribe the voice note"
                  />
                </View>
              ) : null}
            </>
          ) : (
            // Voice-only: there is no text yet, so transcription must complete
            // before extraction has anything to read. Same chain a plain voice
            // note follows.
            <TranscriptionBlock
              submissionId={item.serverSubmissionId}
              startLabel="Transcribe this discovery"
              renderWhenCompleted={<ExtractionBlock submissionId={item.serverSubmissionId} />}
            />
          )}
        </View>
      ) : (
        <Text style={styles.itemMeta}>Send this before it can be understood.</Text>
      )}
    </Card>
  );
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

/**
 * Transcription state for any submission carrying audio — a plain 'voice'
 * capture, or (Step 17) an Explore contribution with a voice note. Shared by
 * both rather than duplicated, because the backend treats them identically:
 * one transcription flow, one set of states, one place to render them.
 *
 * Manual and on-demand, same discipline as ExtractionBlock above: no polling,
 * no auto-trigger, backend truth over UI guesswork.
 *
 * `renderWhenCompleted` is what should appear once a transcript actually
 * exists — for a voice note that is the extraction control, since extraction
 * cannot run before there is text to extract from.
 */
function TranscriptionBlock({
  submissionId,
  startLabel,
  renderWhenCompleted,
}: {
  submissionId: string;
  startLabel: string;
  renderWhenCompleted?: React.ReactNode;
}) {
  const [transcription, setTranscription] = useState<TranscriptionResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);

  async function handleTranscribePress() {
    if (checking) return;
    setChecking(true);
    setCheckError(null);
    try {
      setTranscription(await triggerTranscription(submissionId));
    } catch (err) {
      const message =
        err instanceof ApiError || err instanceof NetworkError ? err.message : 'Could not check status.';
      setCheckError(message);
    } finally {
      setChecking(false);
    }
  }

  const status = transcription ? formatTranscriptionStatus(transcription) : null;

  return (
    <>
      {status ? (
        <View style={styles.nestedBadgeRow}>
          <Badge label={status.label} tone={status.tone} />
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
          label={transcription ? 'Check again' : startLabel}
          onPress={handleTranscribePress}
          loading={checking}
          variant="ghost"
          fullWidth={false}
        />
      ) : (
        renderWhenCompleted ?? null
      )}
    </>
  );
}

// Playback of already-saved recordings is intentionally out of scope here
// (record -> save -> sync -> server reference only) -- this item shows metadata
// only, never a fake "play" affordance. (Preview during composition is a
// different thing and does exist; see VoiceNoteComposer.)
function VoiceItem({ item }: { item: LocalCapture }) {
  const badge = syncBadge(item.syncStatus);

  return (
    <Card style={styles.item}>
      <View style={styles.itemHeaderRow}>
        <View style={styles.itemTypeRow}>
          <Ionicons name="mic-outline" size={13} color={colors.inkFaint} />
          <Text style={styles.itemType}>Voice</Text>
        </View>
        <Text style={styles.itemDate}>{new Date(item.createdAt).toLocaleDateString()}</Text>
      </View>
      <Text style={styles.itemText}>{formatDurationOrUnknown(item.audioDurationMillis)}</Text>
      <View style={styles.itemBadgeRow}>
        <Badge label={badge.label} tone={badge.tone} icon={badge.icon} />
      </View>
      {item.syncStatus === 'failed' && item.lastSyncError ? (
        <Text style={styles.nestedErrorText}>{item.lastSyncError}</Text>
      ) : null}

      {item.serverSubmissionId ? (
        <View style={styles.nestedBlock}>
          <TranscriptionBlock
            submissionId={item.serverSubmissionId}
            startLabel="Listen to this recording"
            // Extraction only makes sense once a transcript actually exists.
            renderWhenCompleted={<ExtractionBlock submissionId={item.serverSubmissionId} />}
          />
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

  // Spinner only for a genuine pull — this screen's `loading` also covers its
  // initial mount, which must not draw the pull indicator.
  const { pulling, onPull } = usePullToRefresh(load);

  const notes = byNeedsAttentionFirst(captures.filter((c) => c.captureType === 'note'));
  const voiceCaptures = byNeedsAttentionFirst(captures.filter((c) => c.captureType === 'voice'));
  const exploreCaptures = byNeedsAttentionFirst(captures.filter((c) => c.captureType === 'explore'));
  const sortedLocations = byNeedsAttentionFirst(locations);
  const isEmpty =
    notes.length === 0 &&
    voiceCaptures.length === 0 &&
    exploreCaptures.length === 0 &&
    sortedLocations.length === 0;

  return (
    <Screen onRefresh={onPull} refreshing={pulling}>
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
          message="Notes, voice updates, discoveries, and locations you save will show up here."
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

          <SectionHeader title="Discoveries" meta={String(exploreCaptures.length)} />
          {exploreCaptures.length === 0 ? (
            <Text style={styles.emptyText}>Nothing shared from Explore yet.</Text>
          ) : (
            exploreCaptures.map((item) => <ExploreItem key={item.id} item={item} />)
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
  itemTextMuted: { ...type.body, color: colors.inkSoft, marginBottom: spacing.xs, fontStyle: 'italic' },
  itemBadgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: 2 },
  itemMeta: { ...type.caption, color: colors.inkFaint, marginTop: spacing.sm, fontStyle: 'italic' },
  itemMetaTop: { ...type.caption, color: colors.inkFaint, marginBottom: spacing.xs },
  nestedBlock: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    gap: spacing.xs,
    alignItems: 'flex-start',
  },
  nestedBadgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  nestedDivider: {
    marginTop: spacing.xs,
    paddingTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    alignSelf: 'stretch',
    alignItems: 'flex-start',
    gap: spacing.xs,
  },
  nestedQuoteText: { ...type.small, color: colors.ink, fontStyle: 'italic' },
  nestedDetailText: { ...type.small, color: colors.ink },
  nestedErrorText: { ...type.caption, color: colors.fix },
});
