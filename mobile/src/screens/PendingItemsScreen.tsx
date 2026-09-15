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
import { listAnswersForGuide } from '../repositories/answerRepository';
import { listCaptures } from '../repositories/captureRepository';
import { listLocations } from '../repositories/locationRepository';
import { syncAll } from '../sync/syncService';
import { colors, spacing, type } from '../theme/theme';
import type {
  LocalAnswer,
  LocalCapture,
  LocalGuide,
  LocalLocation,
  SubmissionReviewStatus,
  SyncStatus,
} from '../types/models';

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

// Admin-approval status (Step 19), rendered on any capture/answer that
// earned a reward (see reward_points_awarded/review_status on both local
// tables). A capture/answer that never earns anything (a plain note) has no
// review row at all, so callers only reach this once they already know a
// reward is at stake -- see the `rewardPoints != null` gate at each call
// site below, mirroring the existing convention for the reward badge itself.
function reviewBadge(status: SubmissionReviewStatus | null): {
  label: string;
  tone: BadgeTone;
  icon: keyof typeof Ionicons.glyphMap;
} {
  switch (status ?? 'pending_review') {
    case 'approved':
      return { label: 'Approved', tone: 'success', icon: 'checkmark-done-circle' };
    case 'rejected':
      return { label: 'Not approved', tone: 'danger', icon: 'close-circle-outline' };
    default:
      return { label: 'Pending admin approval', tone: 'warning', icon: 'hourglass-outline' };
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
/**
 * Renders one Explore-shaped capture (text/photo/voice + sync status). Shared
 * verbatim by 'explore' and 'memory' rows — they are the identical shape on
 * disk (see captureRepository.ts's insertExploreLikeCapture) and differ only
 * in how the section header labels them, via `kindLabel`/`kindIcon`.
 */
function ExploreItem({
  item,
  kindLabel = 'Discovery',
  kindIcon = 'compass-outline',
}: {
  item: LocalCapture;
  kindLabel?: string;
  kindIcon?: keyof typeof Ionicons.glyphMap;
}) {
  const badge = syncBadge(item.syncStatus);
  const uploaded = item.syncStatus === 'uploaded';
  const hasVoice = Boolean(item.localAudioUri);
  const hasText = Boolean(item.textContent?.trim());
  const hasPhoto = Boolean(item.localPhotoUri);

  return (
    <Card style={styles.item}>
      <View style={styles.itemHeaderRow}>
        <View style={styles.itemTypeRow}>
          <Ionicons name={kindIcon} size={13} color={colors.inkFaint} />
          <Text style={styles.itemType}>{kindLabel}</Text>
        </View>
        <Text style={styles.itemDate}>{new Date(item.createdAt).toLocaleDateString()}</Text>
      </View>

      {item.explorePromptTitle ? (
        <Text style={styles.itemMetaTop}>In response to: {item.explorePromptTitle}</Text>
      ) : null}
      {item.locationLabel ? (
        <Text style={styles.itemMetaTop}>Where: {item.locationLabel}</Text>
      ) : null}

      {/* A voice-only (or, for a memory, photo-only) item genuinely has no
          text to show. Saying so is more honest than rendering an empty line
          that looks like a bug. */}
      {hasText ? (
        <Text style={styles.itemText} numberOfLines={4}>
          {item.textContent}
        </Text>
      ) : hasVoice ? (
        <Text style={styles.itemTextMuted}>
          Spoken {kindLabel.toLowerCase()} · {formatDurationOrUnknown(item.audioDurationMillis)}
        </Text>
      ) : hasPhoto ? (
        <Text style={styles.itemTextMuted}>Photo only — no description added.</Text>
      ) : null}

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
        {item.locationSource === 'photo_exif' || item.locationSource === 'gps_live' ? (
          <Badge label="Location verified" tone="success" icon="location" />
        ) : item.locationSource === 'user_selected' ? (
          <Badge label="Place selected" tone="neutral" icon="location-outline" />
        ) : null}
        {/* Admin-approval gate (Step 19) -- see the identical reasoning on
            AnswerItem above. A discovery earns nothing until an admin
            approves it, regardless of how long ago it reached the server. */}
        {uploaded && item.rewardPoints != null && item.rewardPoints > 0 ? (
          <Badge {...reviewBadge(item.reviewStatus)} />
        ) : null}
        {item.reviewStatus === 'approved' ? (
          <Badge
            label={`${item.rewardPointsAwarded ?? item.rewardPoints} pts`}
            tone="success"
            icon="ribbon-outline"
          />
        ) : item.rewardPoints != null && item.rewardPoints > 0 && item.reviewStatus !== 'rejected' ? (
          <Badge label={`${item.rewardPoints} pts if approved`} tone="neutral" icon="ribbon-outline" />
        ) : null}
      </View>

      {item.reviewStatus === 'rejected' && item.rejectionNote ? (
        <Text style={styles.nestedErrorText}>Reason: {item.rejectionNote}</Text>
      ) : null}

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

/**
 * An answer the guide gave to a question — from either source (a knowledge-gap
 * "Still true?" question or a researched place question; see
 * LocalAnswer.questionKind).
 *
 * Answers live in their own table, not local_capture, which is why this is a
 * separate renderer rather than another captureType branch. They have always
 * counted toward the Activity badge (see useLocalActivityCount) but were never
 * LISTED here, so a pending answer showed up as a number with no card behind
 * it. This is that missing card.
 *
 * Reports exactly what the other items report and nothing more: the answer's
 * own text, its real sync status, and — since answers can now carry a photo
 * and a voice note — whether each is still only on this device or has reached
 * the server. The transcription/extraction chain is offered on the same terms
 * as an Explore contribution, because an answer creates the same kind of
 * Submission and goes through the identical backend pipeline.
 */
function AnswerItem({ item }: { item: LocalAnswer }) {
  const badge = syncBadge(item.syncStatus);
  const uploaded = item.syncStatus === 'uploaded';
  const hasVoice = Boolean(item.localAudioUri);
  const hasPhoto = Boolean(item.localPhotoUri);

  return (
    <Card style={styles.item}>
      <View style={styles.itemHeaderRow}>
        <View style={styles.itemTypeRow}>
          <Ionicons name="chatbubble-ellipses-outline" size={13} color={colors.inkFaint} />
          <Text style={styles.itemType}>
            {item.questionKind === 'popular' ? 'Place answer' : 'Answer'}
          </Text>
        </View>
        <Text style={styles.itemDate}>{new Date(item.answeredAt).toLocaleDateString()}</Text>
      </View>

      <Text style={styles.itemText} numberOfLines={4}>
        {item.answerText}
      </Text>

      <View style={styles.itemBadgeRow}>
        <Badge label={badge.label} tone={badge.tone} icon={badge.icon} />
        {hasVoice ? (
          <Badge
            label={uploaded ? 'Voice sent' : 'Voice attached'}
            tone={uploaded ? 'success' : 'info'}
            icon="mic-outline"
          />
        ) : null}
        {hasPhoto ? (
          <Badge
            label={uploaded ? 'Photo sent' : 'Photo attached'}
            tone={uploaded ? 'success' : 'info'}
            icon="image-outline"
          />
        ) : null}
        {/* Admin-approval gate (Step 19): a reward is never earned until an
            admin approves this contribution -- reaching the server is a
            different fact from being paid. Points are shown as PAID only
            once review.status === 'approved'; otherwise this always reads
            as provisional/pending, regardless of sync status, and
            rewardPointsAwarded (not the provisional rewardPoints) is what's
            shown once approved, since a rule's value can differ by then. */}
        {uploaded && item.rewardPoints != null && item.rewardPoints > 0 ? (
          <Badge {...reviewBadge(item.reviewStatus)} />
        ) : null}
        {item.reviewStatus === 'approved' ? (
          <Badge
            label={`${item.rewardPointsAwarded ?? item.rewardPoints} pts`}
            tone="success"
            icon="ribbon-outline"
          />
        ) : item.rewardPoints != null && item.rewardPoints > 0 && item.reviewStatus !== 'rejected' ? (
          <Badge label={`${item.rewardPoints} pts if approved`} tone="neutral" icon="ribbon-outline" />
        ) : null}
      </View>

      {item.reviewStatus === 'rejected' && item.rejectionNote ? (
        <Text style={styles.nestedErrorText}>Reason: {item.rejectionNote}</Text>
      ) : null}

      {item.syncStatus === 'failed' && item.lastSyncError ? (
        <Text style={styles.nestedErrorText}>{item.lastSyncError}</Text>
      ) : null}

      {item.serverSubmissionId ? (
        <View style={styles.nestedBlock}>
          {/* The written answer is always the source for extraction — text is
              required on every answer — so this needs no transcript first. A
              voice note is supplementary and transcribes separately, exactly
              as it does on a text+voice discovery. */}
          <ExtractionBlock submissionId={item.serverSubmissionId} />
          {hasVoice ? (
            <View style={styles.nestedDivider}>
              <TranscriptionBlock
                submissionId={item.serverSubmissionId}
                startLabel="Transcribe the voice note"
              />
            </View>
          ) : null}
        </View>
      ) : uploaded ? (
        // Synced before server_submission_id existed (schema v13). The answer
        // genuinely reached the server, so telling the guide to send it again
        // would be a lie — we simply have no submission id on this device to
        // key transcription/extraction on.
        <Text style={styles.itemMeta}>
          Sent before this device started recording the submission link — answered on the
          server, but not checkable from here.
        </Text>
      ) : (
        <Text style={styles.itemMeta}>Send this answer before it can be understood.</Text>
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
  const [answers, setAnswers] = useState<LocalAnswer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [captureRows, locationRows, answerRows] = await Promise.all([
        listCaptures(db, guide.id),
        listLocations(db, guide.id),
        listAnswersForGuide(db, guide.id),
      ]);
      setCaptures(captureRows);
      setLocations(locationRows);
      setAnswers(answerRows);
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

  /**
   * Send from here, rather than making the guide navigate to Home.
   *
   * This is the screen that shows "Waiting to send" on every card, so it is
   * where the intent to send actually forms — but the only sync control lived
   * on Home, which meant reading the problem in one place and fixing it in
   * another. Same syncAll() Home calls, so the two can never diverge, and
   * syncAll's own in-flight guard means a tap here while Home's sync is still
   * running joins that run instead of starting a second one.
   */
  async function handleSyncNow() {
    if (syncing) return;
    setSyncing(true);
    setSyncMessage(null);
    try {
      const result = await syncAll(db);
      setSyncMessage(result.guideError ? `Sync could not run: ${result.guideError}` : result.message);
    } catch (err) {
      console.error('[PendingItemsScreen] Sync failed:', err);
      setSyncMessage('Sync could not run. Please try again.');
    } finally {
      setSyncing(false);
      // Re-read regardless of outcome: statuses and error messages on the
      // cards below have almost certainly changed, including on failure.
      await load();
    }
  }

  const notes = byNeedsAttentionFirst(captures.filter((c) => c.captureType === 'note'));
  const voiceCaptures = byNeedsAttentionFirst(captures.filter((c) => c.captureType === 'voice'));
  const exploreCaptures = byNeedsAttentionFirst(captures.filter((c) => c.captureType === 'explore'));
  const memoryCaptures = byNeedsAttentionFirst(captures.filter((c) => c.captureType === 'memory'));
  const sortedAnswers = byNeedsAttentionFirst(answers);
  const sortedLocations = byNeedsAttentionFirst(locations);
  // What is genuinely still on this device. 'uploading' counts: a run that was
  // killed mid-flight leaves rows stuck there, and they DO need sending again
  // (see SYNCABLE_STATUSES in the repositories).
  const unsent = [...captures, ...locations, ...answers].filter(
    (item) => item.syncStatus === 'pending' || item.syncStatus === 'failed' || item.syncStatus === 'uploading'
  );
  const failedCount = unsent.filter((item) => item.syncStatus === 'failed').length;
  const isEmpty =
    notes.length === 0 &&
    voiceCaptures.length === 0 &&
    exploreCaptures.length === 0 &&
    memoryCaptures.length === 0 &&
    sortedAnswers.length === 0 &&
    sortedLocations.length === 0;

  return (
    <Screen onRefresh={onPull} refreshing={pulling}>
      <View style={styles.header}>
        <Text style={styles.title}>Activity</Text>
        <Text style={styles.subtitle}>Everything saved on this device — status shows what's actually reached the server.</Text>
      </View>

      {/* Only when there is genuinely something to send. When everything has
          reached the server this bar disappears entirely rather than sitting
          there as a button that would do nothing — the cards below already
          say "Sent to server", which is the honest answer. */}
      {unsent.length > 0 ? (
        <Card style={styles.syncBar}>
          <View style={styles.syncBarRow}>
            <Ionicons
              name={failedCount > 0 ? 'alert-circle-outline' : 'cloud-upload-outline'}
              size={19}
              color={failedCount > 0 ? colors.fix : colors.info}
            />
            <View style={styles.syncBarText}>
              <Text style={styles.syncBarTitle}>
                {unsent.length} item{unsent.length === 1 ? '' : 's'} waiting to send
              </Text>
              <Text style={styles.syncBarSubtitle}>
                {failedCount > 0
                  ? `${failedCount} failed earlier — nothing is lost, they retry on every sync.`
                  : 'Nothing is lost. Send whenever you have a connection.'}
              </Text>
            </View>
            <Button
              label={syncing ? 'Syncing…' : 'Sync now'}
              onPress={handleSyncNow}
              loading={syncing}
              variant="secondary"
              fullWidth={false}
            />
          </View>
          {syncMessage ? <Text style={styles.syncBarResult}>{syncMessage}</Text> : null}
        </Card>
      ) : syncMessage ? (
        // Everything went out on that last tap -- report it, then let the
        // green "Sent to server" badges below carry the state.
        <Text style={styles.syncBarResultAlone}>{syncMessage}</Text>
      ) : null}

      {error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : isEmpty && !loading ? (
        <EmptyState
          icon="file-tray-outline"
          title="Nothing captured yet"
          message="Notes, voice updates, discoveries, memories, answers, and locations you save will show up here."
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

          <SectionHeader title="Memories" meta={String(memoryCaptures.length)} />
          {memoryCaptures.length === 0 ? (
            <Text style={styles.emptyText}>No memories shared yet.</Text>
          ) : (
            memoryCaptures.map((item) => (
              <ExploreItem key={item.id} item={item} kindLabel="Memory" kindIcon="images-outline" />
            ))
          )}

          <SectionHeader title="Answers" meta={String(sortedAnswers.length)} />
          {sortedAnswers.length === 0 ? (
            <Text style={styles.emptyText}>No questions answered yet.</Text>
          ) : (
            sortedAnswers.map((item) => <AnswerItem key={item.id} item={item} />)
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
  syncBar: { marginBottom: spacing.md },
  syncBarRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  syncBarText: { flex: 1 },
  syncBarTitle: { ...type.smallBold, color: colors.ink },
  syncBarSubtitle: { ...type.caption, color: colors.inkFaint, marginTop: 2, lineHeight: 16 },
  syncBarResult: { ...type.caption, color: colors.inkSoft, marginTop: spacing.sm, lineHeight: 16 },
  syncBarResultAlone: {
    ...type.caption,
    color: colors.inkSoft,
    marginBottom: spacing.md,
    lineHeight: 16,
  },
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
