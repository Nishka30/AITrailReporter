import { useCallback, useEffect, useState } from 'react';
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import type { PlaceQuestion } from '../api/placeQuestions';
import type { Question } from '../api/questions';
import type { RecordedAudio } from '../audio/audioRecordingService';
import { AppHeader, Badge, Button, Card, LoadingState, RewardChip, Screen } from '../components/ui';
import VoiceNoteComposer from '../components/VoiceNoteComposer';
import { choosePhoto, takePhoto, type PhotoPickResult } from '../photo/photoPickerService';
import { createAnswer, getAnswerByQuestionId } from '../repositories/answerRepository';
import { colors, spacing, type } from '../theme/theme';
import type { LocalAnswer, LocalGuide, QuestionKind } from '../types/models';

type AttachedPhoto = { uri: string; contentType: string };

/**
 * A question to answer, normalized across the TWO sources (Step 18).
 *
 * The screen takes this rather than a Question | PlaceQuestion union so it
 * doesn't branch on source in a dozen places: composing, saving offline and
 * showing an already-saved answer are identical for both, and the only real
 * differences (header, context line, whether the server can report an answer
 * from another device) are resolved once, here, by the builders below.
 */
export interface AnswerTarget {
  kind: QuestionKind;
  /** Backend Question id, or PlaceQuestion id — see LocalAnswer.questionKind. */
  id: string;
  headerTitle: string;
  questionText: string;
  /** Backend-issued; 0 means "no active rule", and the chip is then hidden. */
  rewardPoints: number;
  safetyCritical: boolean;
  /** Short "why you're being asked" line; null when there isn't an honest one. */
  contextLabel: string | null;
  placeLine: string | null;
  /** An answer the SERVER already has (only possible for a priority question,
   * which is assigned to exactly one guide). Null for popular questions —
   * several guides answering the same one is legitimate, so there is no
   * "already answered elsewhere" state to report. */
  serverAnsweredText: string | null;
}

function gapContextLabel(question: Question): string | null {
  if (question.assignment?.status === 'completed') return null;
  switch (question.gapState) {
    case 'missing':
      return 'No report yet from this area';
    case 'aging':
      return 'Getting old — a quick confirmation helps';
    case 'stale':
      return 'The last report here is out of date';
    default:
      return null;
  }
}

/** Builds an AnswerTarget from a knowledge-gap question. */
export function targetFromQuestion(question: Question): AnswerTarget {
  return {
    kind: 'dynamic',
    id: question.id,
    headerTitle: question.displayName,
    questionText: question.questionText ?? question.displayName,
    rewardPoints: question.rewardPoints,
    safetyCritical: question.safetyCritical,
    contextLabel: gapContextLabel(question),
    placeLine: question.nearestKnownPlaceName
      ? `Near ${question.nearestKnownPlaceName}${
          question.nearestKnownPlaceDistanceMeters != null
            ? ` (~${Math.round(question.nearestKnownPlaceDistanceMeters)}m)`
            : ''
        }`
      : null,
    serverAnsweredText: question.answer?.answerText ?? null,
  };
}

/** Builds an AnswerTarget from a researched popular question. */
export function targetFromPlaceQuestion(
  question: PlaceQuestion,
  placeName: string | null
): AnswerTarget {
  return {
    kind: 'popular',
    id: question.id,
    headerTitle: placeName ?? 'Popular question',
    questionText: question.questionText,
    rewardPoints: question.rewardPoints,
    // A popular question is never safety-classified: it wasn't derived from a
    // safety-critical knowledge type, and claiming otherwise would misuse the
    // one badge that has to stay reliable.
    safetyCritical: false,
    contextLabel: 'Commonly asked about this place',
    placeLine: placeName ? `About ${placeName}` : null,
    serverAnsweredText: null,
  };
}

type Props = {
  guide: LocalGuide;
  target: AnswerTarget;
  onDone: () => void;
};

/**
 * Answer composition for one question (Step 13, restyled Step 15, extended to
 * both question sources in Step 18).
 *
 * Offline-first, unchanged: saving writes to SQLite immediately and returns —
 * it never waits on, or depends on, a network response. The answer enters the
 * existing sync engine (src/sync/syncService.ts) and is uploaded next time
 * "Sync now" runs, exactly like a note or a location. The reward is recorded
 * locally as PENDING and only becomes real when the backend confirms it.
 *
 * If this question was already answered on this device (regardless of whether
 * that answer has synced yet), the compose form is never shown again — there
 * is no edit/re-answer flow.
 */
export default function AnswerQuestionScreen({ guide, target, onDone }: Props) {
  const db = useSQLiteContext();
  const [existingAnswer, setExistingAnswer] = useState<LocalAnswer | null | undefined>(undefined);
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);
  const [voice, setVoice] = useState<RecordedAudio | null>(null);
  const [photo, setPhoto] = useState<AttachedPhoto | null>(null);
  const [pickingPhoto, setPickingPhoto] = useState(false);
  const [photoNotice, setPhotoNotice] = useState<string | null>(null);

  function applyPhotoResult(result: PhotoPickResult) {
    switch (result.status) {
      case 'success':
        setPhoto({ uri: result.uri, contentType: result.contentType });
        setPhotoNotice(null);
        break;
      case 'cancelled':
        // Not an error, and not worth a message — the guide chose to back out.
        break;
      case 'permission-denied':
        setPhotoNotice(
          result.canAskAgain
            ? 'Photo permission is needed for this. Please allow it and try again.'
            : 'Photo permission was denied. You can enable it for this app in your device settings.'
        );
        break;
      case 'error':
        setPhotoNotice(result.message);
        break;
    }
  }

  async function handlePickPhoto(useCamera: boolean) {
    if (pickingPhoto || saving) return;
    setPickingPhoto(true);
    setPhotoNotice(null);
    try {
      applyPhotoResult(useCamera ? await takePhoto() : await choosePhoto());
    } finally {
      setPickingPhoto(false);
    }
  }

  const loadExisting = useCallback(async () => {
    try {
      setExistingAnswer(await getAnswerByQuestionId(db, target.id));
    } catch (err) {
      console.error('[AnswerQuestionScreen] Failed to read local answer:', err);
      setExistingAnswer(null);
    }
  }, [db, target.id]);

  useEffect(() => {
    loadExisting();
  }, [loadExisting]);

  async function handleSave() {
    if (saving) return;
    const trimmed = text.trim();
    // Text is REQUIRED here even when a voice note or photo is attached, and
    // that is a backend contract rather than a style choice: both answer
    // endpoints declare answer_text with min_length=1 and an explicit
    // not-blank validator, so a media-only answer would save locally and then
    // fail with a 422 on every sync attempt forever. The media is additive to
    // the written answer, not a replacement for it.
    //
    // (This is the one place it differs from ExploreContributeScreen, which
    // posts a submission rather than an answer and so can accept a voice note
    // with no text at all.)
    if (!trimmed) {
      setError(
        voice || photo
          ? 'Add a few words as well — an answer needs some text alongside the recording or photo.'
          : 'Please enter an answer before saving.'
      );
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createAnswer(
        db,
        guide.id,
        target.id,
        trimmed,
        new Date().toISOString(),
        target.kind,
        // Snapshot what the BACKEND said this was worth, so the pending-points
        // line is a real server-issued number rather than a device guess.
        // 0 means no active rule, which we store as null (earned nothing).
        target.rewardPoints > 0 ? target.rewardPoints : null,
        {
          localAudioUri: voice?.uri ?? null,
          audioDurationMillis: voice?.durationMillis ?? null,
          audioContentType: voice?.contentType ?? null,
          localPhotoUri: photo?.uri ?? null,
          photoContentType: photo?.contentType ?? null,
        }
      );
      setJustSaved(true);
      await loadExisting();
    } catch (err) {
      console.error('[AnswerQuestionScreen] Failed to save local answer:', err);
      setError('Could not save this answer on your device. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen>
        <AppHeader title={target.headerTitle} onBack={onDone} />

        <Card style={styles.questionCard}>
          <View style={styles.badgeRow}>
            {target.safetyCritical ? <Badge label="Safety" tone="danger" icon="warning-outline" /> : null}
            {target.contextLabel ? <Badge label={target.contextLabel} tone="neutral" /> : null}
          </View>
          <Text style={styles.questionText}>{target.questionText}</Text>
          {target.placeLine ? (
            <View style={styles.placeRow}>
              <Ionicons name="location-outline" size={13} color={colors.inkFaint} />
              <Text style={styles.placeText}>{target.placeLine}</Text>
            </View>
          ) : null}
          {!existingAnswer && target.rewardPoints > 0 ? (
            <View style={styles.rewardRow}>
              <RewardChip points={target.rewardPoints} />
            </View>
          ) : null}
        </Card>

        {existingAnswer === undefined ? (
          <LoadingState message="Checking for a saved answer…" />
        ) : existingAnswer ? (
          <AnsweredCard answer={existingAnswer} justSaved={justSaved} onDone={onDone} />
        ) : target.serverAnsweredText ? (
          <AnsweredElsewhereCard answerText={target.serverAnsweredText} onDone={onDone} />
        ) : (
          <>
            <Text style={styles.composeLabel}>Your answer</Text>
            <TextInput
              style={styles.textArea}
              placeholder="Type what you see…"
              placeholderTextColor={colors.inkFaint}
              value={text}
              onChangeText={setText}
              multiline
              numberOfLines={6}
              autoFocus
              editable={!saving}
            />

            {/* Both optional, both additive to the text answer. Standing in
                front of the thing being asked about is exactly when a picture
                or a spoken reply is the easiest and most accurate way to
                answer -- and the backend already supports it, because an
                answer creates a Submission just like a capture does (see
                backend/app/services/question_answers.py). */}
            <Text style={styles.mediaLabel}>
              <Ionicons name="mic-outline" size={13} color={colors.inkFaint} /> Voice note
              <Text style={styles.mediaHint}>
                {voice ? '  ·  Attached' : '  ·  Optional — record alongside your answer'}
              </Text>
            </Text>
            <View style={styles.voiceWrap}>
              <VoiceNoteComposer
                value={voice}
                onChange={setVoice}
                idleCopy="Say your answer out loud"
                disabled={saving}
              />
            </View>

            <Text style={styles.mediaLabel}>
              <Ionicons name="camera-outline" size={13} color={colors.inkFaint} /> Photo
              <Text style={styles.mediaHint}>  ·  Optional</Text>
            </Text>
            {photo ? (
              <View style={styles.photoWrap}>
                <Image source={{ uri: photo.uri }} style={styles.photoPreview} resizeMode="cover" />
                <Pressable
                  onPress={() => setPhoto(null)}
                  accessibilityRole="button"
                  accessibilityLabel="Remove photo"
                  hitSlop={8}
                  style={styles.photoRemove}
                  disabled={saving}
                >
                  <Ionicons name="close" size={17} color={colors.white} />
                </Pressable>
              </View>
            ) : (
              <View style={styles.photoActions}>
                <Pressable
                  onPress={() => handlePickPhoto(true)}
                  accessibilityRole="button"
                  accessibilityLabel="Take photo"
                  disabled={pickingPhoto || saving}
                  style={({ pressed }) => [
                    styles.photoAction,
                    pressed && styles.photoActionPressed,
                    (pickingPhoto || saving) && styles.photoActionDisabled,
                  ]}
                >
                  <Ionicons name="camera-outline" size={21} color={colors.marigoldDeep} />
                  <Text style={styles.photoActionText}>Take photo</Text>
                </Pressable>
                <Pressable
                  onPress={() => handlePickPhoto(false)}
                  accessibilityRole="button"
                  accessibilityLabel="Choose photo"
                  disabled={pickingPhoto || saving}
                  style={({ pressed }) => [
                    styles.photoAction,
                    pressed && styles.photoActionPressed,
                    (pickingPhoto || saving) && styles.photoActionDisabled,
                  ]}
                >
                  <Ionicons name="images-outline" size={21} color={colors.marigoldDeep} />
                  <Text style={styles.photoActionText}>Choose photo</Text>
                </Pressable>
              </View>
            )}
            {photoNotice ? <Text style={styles.notice}>{photoNotice}</Text> : null}

            {error ? <Text style={styles.error}>{error}</Text> : null}

            <Button label={saving ? 'Saving…' : 'Save answer'} onPress={handleSave} loading={saving} />

            <Text style={styles.footnote}>
              Saved on this device right away. It's sent the next time you sync — no connection needed now.
            </Text>
          </>
        )}
      </Screen>
    </KeyboardAvoidingView>
  );
}

function AnsweredCard({
  answer,
  justSaved,
  onDone,
}: {
  answer: LocalAnswer;
  justSaved: boolean;
  onDone: () => void;
}) {
  const confirmed = answer.syncStatus === 'uploaded';
  const status = confirmed
    ? { label: 'Sent to the server', tone: 'success' as const, icon: 'checkmark-circle' as const }
    : answer.syncStatus === 'failed'
      ? { label: 'Send failed — will retry on next sync', tone: 'danger' as const, icon: 'alert-circle-outline' as const }
      : answer.syncStatus === 'uploading'
        ? { label: 'Sending…', tone: 'info' as const, icon: 'sync-outline' as const }
        : { label: 'Saved — waiting to send', tone: 'info' as const, icon: 'cloud-upload-outline' as const };

  // Admin-approval gate (Step 19): a reward is never earned until an admin
  // approves this specific contribution -- being SENT to the server is a
  // different fact from being PAID for. `reviewStatus` is null until sync
  // has happened at least once AND a subsequent poll has reported back (see
  // sync/submissionReviewSync.ts), so it is treated the same as
  // 'pending_review' rather than shown as anything more final.
  const reviewStatus = answer.reviewStatus ?? 'pending_review';

  return (
    <Card variant="outline" style={styles.answeredCard}>
      <Text style={styles.answeredLabel}>{justSaved ? 'Saved!' : 'Your answer'}</Text>
      <Text style={styles.answeredText}>{answer.answerText}</Text>
      <Badge label={status.label} tone={status.tone} icon={status.icon} />

      {confirmed && reviewStatus === 'approved' ? (
        <>
          <Badge label="Approved" tone="success" icon="checkmark-done-circle" />
          <RewardChip points={answer.rewardPointsAwarded ?? answer.rewardPoints ?? 0} />
        </>
      ) : confirmed && reviewStatus === 'rejected' ? (
        <>
          <Badge label="Not approved" tone="danger" icon="close-circle-outline" />
          {answer.rejectionNote ? (
            <Text style={styles.rejectionText}>Reason: {answer.rejectionNote}</Text>
          ) : null}
        </>
      ) : (
        <>
          {confirmed ? <Badge label="Pending admin approval" tone="warning" icon="hourglass-outline" /> : null}
          {/* Provisional worth only -- not yet paid either way. Always shown
              as pending here: even once sent, nothing is earned until an
              admin approves it. */}
          {answer.rewardPoints ? <RewardChip points={answer.rewardPoints} pending /> : null}
        </>
      )}

      <View style={styles.doneButtonWrap}>
        <Button label="Back to questions" onPress={onDone} variant="secondary" />
      </View>
    </Card>
  );
}

function AnsweredElsewhereCard({ answerText, onDone }: { answerText: string; onDone: () => void }) {
  return (
    <Card variant="outline" style={styles.answeredCard}>
      <Text style={styles.answeredLabel}>Answer on file</Text>
      <Text style={styles.answeredText}>{answerText}</Text>
      <Badge label="Already answered (another device)" tone="success" icon="checkmark-circle" />
      <View style={styles.doneButtonWrap}>
        <Button label="Back to questions" onPress={onDone} variant="secondary" />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  mediaLabel: {
    ...type.small,
    color: colors.ink,
    fontWeight: '600',
    marginTop: spacing.lg,
    marginBottom: spacing.xs,
  },
  mediaHint: { ...type.caption, color: colors.inkFaint, fontWeight: '400' },
  voiceWrap: { marginBottom: spacing.xs },
  photoWrap: { position: 'relative', marginBottom: spacing.sm },
  photoPreview: { width: '100%', height: 190, borderRadius: 12, backgroundColor: colors.inkFaint },
  photoRemove: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.55)',
  },
  photoActions: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm },
  photoAction: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: spacing.md,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.marigoldSoft,
    backgroundColor: colors.marigoldSoft,
  },
  photoActionPressed: { opacity: 0.7 },
  photoActionDisabled: { opacity: 0.5 },
  photoActionText: { ...type.small, color: colors.marigoldDeep, fontWeight: '600' },
  notice: { ...type.caption, color: colors.inkFaint, marginBottom: spacing.sm },

  flex: { flex: 1 },
  questionCard: { marginBottom: spacing.md },
  badgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm },
  questionText: { ...type.subtitle, color: colors.ink, lineHeight: 24 },
  placeRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: spacing.sm },
  placeText: { ...type.caption, color: colors.inkFaint },
  rewardRow: { flexDirection: 'row', marginTop: spacing.sm },
  composeLabel: { ...type.captionBold, color: colors.inkFaint, letterSpacing: 0.4, marginBottom: spacing.xs },
  textArea: {
    backgroundColor: colors.paperElevated,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: spacing.md,
    ...type.body,
    color: colors.ink,
    minHeight: 140,
    textAlignVertical: 'top',
    marginBottom: spacing.md,
  },
  error: { ...type.small, color: colors.fix, marginBottom: spacing.sm },
  footnote: { ...type.caption, color: colors.inkFaint, marginTop: spacing.md, lineHeight: 17, textAlign: 'center' },
  answeredCard: { alignItems: 'flex-start', gap: spacing.sm },
  answeredLabel: { ...type.captionBold, color: colors.inkFaint, letterSpacing: 0.4 },
  answeredText: { ...type.body, color: colors.ink, lineHeight: 22 },
  rejectionText: { ...type.caption, color: colors.fix, lineHeight: 18 },
  doneButtonWrap: { alignSelf: 'stretch', marginTop: spacing.xs },
});
