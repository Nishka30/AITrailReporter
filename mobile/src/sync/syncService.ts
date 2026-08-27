import { File } from 'expo-file-system';
import type { SQLiteDatabase } from 'expo-sqlite';

import { uploadSubmissionAudio } from '../api/audio';
import { ApiError, NetworkError } from '../api/client';
import { createOrGetGuide } from '../api/guides';
import { createOrGetLocation } from '../api/locations';
import { uploadSubmissionPhoto } from '../api/photos';
import { submitAnswer } from '../api/questionAnswers';
import { createOrGetSubmission } from '../api/submissions';
import {
  listSyncableAnswers,
  markAnswerFailed,
  markAnswerUploaded,
  markAnswerUploading,
} from '../repositories/answerRepository';
import {
  listSyncableCaptures,
  markCaptureFailed,
  markCaptureUploaded,
  markCaptureUploading,
} from '../repositories/captureRepository';
import { getCurrentLocalGuide, setServerGuideId } from '../repositories/guideRepository';
import {
  listSyncableLocations,
  markLocationFailed,
  markLocationUploaded,
  markLocationUploading,
} from '../repositories/locationRepository';
import type { CaptureType, LocalAnswer, LocalCapture, LocalGuide, LocalLocation } from '../types/models';

export interface CaptureSyncOutcome {
  captureId: number;
  captureType: CaptureType;
  status: 'uploaded' | 'failed';
  message?: string;
}

export interface LocationSyncOutcome {
  locationId: number;
  status: 'uploaded' | 'failed';
  message?: string;
}

export interface AnswerSyncOutcome {
  answerId: number;
  status: 'uploaded' | 'failed';
  message?: string;
}

export interface CaptureSyncSummary {
  attempted: number;
  uploaded: number;
  failed: number;
  outcomes: CaptureSyncOutcome[];
}

export interface LocationSyncSummary {
  attempted: number;
  uploaded: number;
  failed: number;
  outcomes: LocationSyncOutcome[];
}

export interface AnswerSyncSummary {
  attempted: number;
  uploaded: number;
  failed: number;
  outcomes: AnswerSyncOutcome[];
}

export interface SyncResult {
  ranAt: string;
  /** True once the guide has (or already had) a serverGuideId after this run. */
  guideSynced: boolean;
  guideError: string | null;
  /** Text notes only — kept distinct from `voice` (not a merged "captures"
   * bucket) so the UI can report on each kind without parsing outcome lists. */
  notes: CaptureSyncSummary;
  voice: CaptureSyncSummary;
  /** Explore discovery contributions (Step 16) — reported separately from
   * `notes` for the same reason voice is: they are a distinct thing the guide
   * did, and folding them into "notes uploaded" would misdescribe the work. */
  explore: CaptureSyncSummary;
  locations: LocationSyncSummary;
  /** Answers to assigned questions (Step 13) — synced independently of
   * notes/voice/locations; one failed answer never blocks the others. */
  answers: AnswerSyncSummary;
  /** Short, user-facing summary — the UI should show this, not re-derive its own. */
  message: string;
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof NetworkError) return err.message;
  if (err instanceof Error) return err.message;
  return 'Unknown sync error.';
}

function emptySummary<T>(): { attempted: number; uploaded: number; failed: number; outcomes: T[] } {
  return { attempted: 0, uploaded: 0, failed: 0, outcomes: [] };
}

function emptyResult(message: string): SyncResult {
  return {
    ranAt: new Date().toISOString(),
    guideSynced: false,
    guideError: null,
    notes: emptySummary<CaptureSyncOutcome>(),
    voice: emptySummary<CaptureSyncOutcome>(),
    explore: emptySummary<CaptureSyncOutcome>(),
    locations: emptySummary<LocationSyncOutcome>(),
    answers: emptySummary<AnswerSyncOutcome>(),
    message,
  };
}

type GuideResolution = { serverGuideId: string } | { error: string };

/** STEP 1 of the outbox flow: ensure the guide exists on the backend. */
async function ensureServerGuideId(
  db: SQLiteDatabase,
  guide: LocalGuide
): Promise<GuideResolution> {
  if (guide.serverGuideId) {
    return { serverGuideId: guide.serverGuideId };
  }
  try {
    const serverGuide = await createOrGetGuide({
      name: guide.name,
      phoneNumber: guide.phoneNumber,
      clientGuideId: guide.clientGuideId,
    });
    await setServerGuideId(db, guide.id, serverGuide.id);
    return { serverGuideId: serverGuide.id };
  } catch (err) {
    return { error: describeError(err) };
  }
}

/** Sync a text note: a single request that both creates the submission and
 * carries its full content. */
async function syncOneNote(serverGuideId: string, capture: LocalCapture): Promise<string> {
  const submission = await createOrGetSubmission({
    guideId: serverGuideId,
    clientSubmissionId: capture.clientSubmissionId,
    captureType: 'note',
    textContent: capture.textContent ?? '',
    submittedAt: capture.createdAt,
  });
  return submission.id;
}

/**
 * Sync a voice recording: TWO requests, both idempotent, so a retry after
 * either one's response is lost never creates a duplicate submission or a
 * duplicate audio attachment —
 *
 *   1. Resolve/create the server Submission (idempotent on clientSubmissionId —
 *      same as a note). Cheap to repeat even if this exact stage already
 *      succeeded on a prior failed attempt: the backend just returns the
 *      existing submission.
 *   2. Upload the audio file, attached to that submission (idempotent on the
 *      SEPARATE clientAudioId). If step 1 succeeds but step 2 throws, this
 *      capture is marked 'failed' and retried from step 1 next sync — which is
 *      safe and cheap for the reason above, not a correctness risk.
 *
 * This is why no intermediate "submission created, audio pending" local status
 * is needed beyond the existing pending/uploading/failed/uploaded states: both
 * stages are safely re-executable from scratch on every retry.
 */
async function syncOneVoiceCapture(serverGuideId: string, capture: LocalCapture): Promise<string> {
  if (!capture.localAudioUri || !capture.clientAudioId) {
    // Should be unreachable — createVoiceCapture always sets both — but this is
    // local data, not a network response, so fail loudly rather than guessing.
    throw new Error('Voice capture is missing its local audio file reference.');
  }

  // React Native's fetch throws the SAME generic "Network request failed"
  // error whether the server is genuinely unreachable OR a FormData file part
  // points at a URI that no longer exists on disk — there is no way to tell
  // those apart from the fetch() rejection alone (see api/audio.ts). Checking
  // existence explicitly here, before ever calling fetch, means a missing
  // recording gets its own honest, specific message instead of silently
  // masquerading as a connectivity problem (which sent guides chasing their
  // network/firewall setup for a problem no retry could ever fix).
  const file = new File(capture.localAudioUri);
  if (!file.exists) {
    throw new Error(
      'This recording is no longer on your device (it may have been cleared by the OS or the ' +
        'app was reinstalled). It cannot be sent — record a new voice update instead.'
    );
  }

  const submission = await createOrGetSubmission({
    guideId: serverGuideId,
    clientSubmissionId: capture.clientSubmissionId,
    captureType: 'voice',
    textContent: null,
    submittedAt: capture.createdAt,
  });
  await uploadSubmissionAudio({
    submissionId: submission.id,
    clientAudioId: capture.clientAudioId,
    localUri: capture.localAudioUri,
    contentType: capture.audioContentType ?? 'audio/m4a',
    durationSeconds:
      capture.audioDurationMillis != null ? capture.audioDurationMillis / 1000 : null,
  });
  return submission.id;
}

/**
 * Sync an Explore contribution (Step 16): ONE request if it's text-only, TWO
 * if it carries a photo — deliberately the same two-stage, both-idempotent
 * shape as syncOneVoiceCapture above, for the same reasons:
 *
 *   1. Create/resolve the server Submission (idempotent on
 *      clientSubmissionId). Its text_content is what the existing extraction
 *      pipeline will later turn into observations.
 *   2. If and only if a photo is attached, upload it against the SEPARATE
 *      clientPhotoId. If step 1 succeeds and step 2 throws, the capture is
 *      marked 'failed' and retried from step 1 next sync — safe and cheap,
 *      because step 1 just returns the existing submission on replay.
 *
 * The photo is genuinely optional here, which is the one structural difference
 * from voice: a voice capture without audio is meaningless, whereas a
 * text-only Explore contribution is complete and useful on its own.
 */
async function syncOneExploreCapture(
  serverGuideId: string,
  capture: LocalCapture
): Promise<string> {
  const text = (capture.textContent ?? '').trim();
  if (!text) {
    // Should be unreachable — createExploreCapture always requires text — but
    // this is local data, not a network response, so fail loudly rather than
    // sending an empty submission the backend would reject anyway.
    throw new Error('This Explore contribution has no text and cannot be sent.');
  }

  const submission = await createOrGetSubmission({
    guideId: serverGuideId,
    clientSubmissionId: capture.clientSubmissionId,
    captureType: 'explore',
    textContent: text,
    submittedAt: capture.createdAt,
  });

  if (capture.localPhotoUri && capture.clientPhotoId) {
    // Same honest existence check as voice: a picked photo whose file has been
    // reclaimed must report that specifically, never as a network failure.
    const file = new File(capture.localPhotoUri);
    if (!file.exists) {
      throw new Error(
        'The photo for this contribution is no longer on your device. Its text can be ' +
          'sent, but the photo must be added again.'
      );
    }
    await uploadSubmissionPhoto({
      submissionId: submission.id,
      clientPhotoId: capture.clientPhotoId,
      localUri: capture.localPhotoUri,
      contentType: capture.photoContentType ?? 'image/jpeg',
    });
  }

  return submission.id;
}

/** STEP 2 of the outbox flow: sync one capture (note, voice, or explore).
 * Never throws — always resolves. */
async function syncOneCapture(
  db: SQLiteDatabase,
  serverGuideId: string,
  capture: LocalCapture
): Promise<CaptureSyncOutcome> {
  await markCaptureUploading(db, capture.id);
  try {
    let serverSubmissionId: string;
    if (capture.captureType === 'note') {
      serverSubmissionId = await syncOneNote(serverGuideId, capture);
    } else if (capture.captureType === 'voice') {
      serverSubmissionId = await syncOneVoiceCapture(serverGuideId, capture);
    } else if (capture.captureType === 'explore') {
      serverSubmissionId = await syncOneExploreCapture(serverGuideId, capture);
    } else {
      // Step 7 only ingests notes and voice — a future capture type reaching
      // here means this build genuinely can't sync it yet, not a transient
      // failure.
      throw new Error(`Capture type "${capture.captureType}" is not supported for sync yet.`);
    }
    await markCaptureUploaded(db, capture.id, serverSubmissionId);
    return { captureId: capture.id, captureType: capture.captureType, status: 'uploaded' };
  } catch (err) {
    const message = describeError(err);
    await markCaptureFailed(db, capture.id, message);
    return { captureId: capture.id, captureType: capture.captureType, status: 'failed', message };
  }
}

/** STEP 3 of the outbox flow: sync one GPS sample. Never throws — always resolves. */
async function syncOneLocation(
  db: SQLiteDatabase,
  serverGuideId: string,
  location: LocalLocation
): Promise<LocationSyncOutcome> {
  await markLocationUploading(db, location.id);
  try {
    const serverLocation = await createOrGetLocation({
      guideId: serverGuideId,
      clientLocationId: location.clientLocationId,
      latitude: location.latitude,
      longitude: location.longitude,
      accuracyMeters: location.accuracyMeters,
      recordedAt: location.recordedAt,
    });
    await markLocationUploaded(db, location.id, serverLocation.id);
    return { locationId: location.id, status: 'uploaded' };
  } catch (err) {
    const message = describeError(err);
    await markLocationFailed(db, location.id, message);
    return { locationId: location.id, status: 'failed', message };
  }
}

/** STEP 4 of the outbox flow: sync one question answer. Never throws —
 * always resolves. Same shape as syncOneLocation. */
async function syncOneAnswer(
  db: SQLiteDatabase,
  serverGuideId: string,
  answer: LocalAnswer
): Promise<AnswerSyncOutcome> {
  await markAnswerUploading(db, answer.id);
  try {
    const question = await submitAnswer({
      questionId: answer.serverQuestionId,
      guideId: serverGuideId,
      clientAnswerId: answer.clientAnswerId,
      answerText: answer.answerText,
      answeredAt: answer.answeredAt,
    });
    if (!question.answer) {
      // Should be unreachable — a successful POST .../answers always returns
      // the question with `answer` populated — but this is a network
      // response, not local data, so fail loudly rather than guessing an id.
      throw new Error('Server did not return the persisted answer.');
    }
    await markAnswerUploaded(db, answer.id, question.answer.id);
    return { answerId: answer.id, status: 'uploaded' };
  } catch (err) {
    const message = describeError(err);
    await markAnswerFailed(db, answer.id, message);
    return { answerId: answer.id, status: 'failed', message };
  }
}

function buildSummaryMessage(
  notes: CaptureSyncSummary,
  voice: CaptureSyncSummary,
  explore: CaptureSyncSummary,
  locations: LocationSyncSummary,
  answers: AnswerSyncSummary
): string {
  const uploaded =
    notes.uploaded + voice.uploaded + explore.uploaded + locations.uploaded + answers.uploaded;
  const failed = notes.failed + voice.failed + explore.failed + locations.failed + answers.failed;
  if (uploaded === 0 && failed === 0) {
    return 'Nothing to sync — everything is already uploaded.';
  }
  const parts: string[] = [];
  if (notes.uploaded > 0) {
    parts.push(`${notes.uploaded} note${notes.uploaded === 1 ? '' : 's'} uploaded`);
  }
  if (voice.uploaded > 0) {
    parts.push(`${voice.uploaded} voice note${voice.uploaded === 1 ? '' : 's'} uploaded`);
  }
  if (explore.uploaded > 0) {
    parts.push(`${explore.uploaded} discovery${explore.uploaded === 1 ? '' : ' items'} uploaded`);
  }
  if (locations.uploaded > 0) {
    parts.push(`${locations.uploaded} location${locations.uploaded === 1 ? '' : 's'} uploaded`);
  }
  if (answers.uploaded > 0) {
    parts.push(`${answers.uploaded} answer${answers.uploaded === 1 ? '' : 's'} uploaded`);
  }
  if (failed > 0) {
    parts.push(`${failed} item${failed === 1 ? '' : 's'} could not be uploaded`);
  }
  return `${parts.join(', ')}.`;
}

async function performSync(db: SQLiteDatabase): Promise<SyncResult> {
  // Ensure guide first — nothing else can be attributed to a server guide until
  // this resolves.
  const guide = await getCurrentLocalGuide(db);
  if (!guide) {
    return emptyResult('No local guide profile exists yet — nothing to sync.');
  }

  const guideResolution = await ensureServerGuideId(db, guide);
  if ('error' in guideResolution) {
    return {
      ...emptyResult(`Could not synchronize the guide profile: ${guideResolution.error}`),
      guideError: guideResolution.error,
    };
  }
  const serverGuideId = guideResolution.serverGuideId;

  // Captures — notes and voice recordings together, pending/failed/(leftover-
  // from-a-crash) uploading; see SYNCABLE_STATUSES in captureRepository.ts.
  // Processed in one oldest-created-first loop (not two separate passes) so a
  // guide's captures sync in the order they were actually made regardless of
  // type; each is independent — one failing does not stop the rest. Results are
  // then split by type below purely for reporting (Task J: the UI must be able
  // to distinguish text vs. audio without parsing outcome lists).
  const syncableCaptures = await listSyncableCaptures(db, guide.id);
  const captureOutcomes: CaptureSyncOutcome[] = [];
  for (const capture of syncableCaptures) {
    captureOutcomes.push(await syncOneCapture(db, serverGuideId, capture));
  }
  const summarize = (outcomes: CaptureSyncOutcome[]): CaptureSyncSummary => ({
    attempted: outcomes.length,
    uploaded: outcomes.filter((o) => o.status === 'uploaded').length,
    failed: outcomes.filter((o) => o.status === 'failed').length,
    outcomes,
  });
  const notes = summarize(captureOutcomes.filter((o) => o.captureType === 'note'));
  const voice = summarize(captureOutcomes.filter((o) => o.captureType === 'voice'));
  const explore = summarize(captureOutcomes.filter((o) => o.captureType === 'explore'));

  // GPS locations — same eligibility/ordering/independence rules as captures, just
  // against the GuideLocation endpoint instead of submissions.
  const syncableLocations = await listSyncableLocations(db, guide.id);
  const locationOutcomes: LocationSyncOutcome[] = [];
  for (const location of syncableLocations) {
    locationOutcomes.push(await syncOneLocation(db, serverGuideId, location));
  }
  const locations: LocationSyncSummary = {
    attempted: locationOutcomes.length,
    uploaded: locationOutcomes.filter((o) => o.status === 'uploaded').length,
    failed: locationOutcomes.filter((o) => o.status === 'failed').length,
    outcomes: locationOutcomes,
  };

  // Question answers (Step 13) — independent of captures/locations above;
  // one failed answer sync does not affect or get affected by the others.
  const syncableAnswers = await listSyncableAnswers(db, guide.id);
  const answerOutcomes: AnswerSyncOutcome[] = [];
  for (const answer of syncableAnswers) {
    answerOutcomes.push(await syncOneAnswer(db, serverGuideId, answer));
  }
  const answers: AnswerSyncSummary = {
    attempted: answerOutcomes.length,
    uploaded: answerOutcomes.filter((o) => o.status === 'uploaded').length,
    failed: answerOutcomes.filter((o) => o.status === 'failed').length,
    outcomes: answerOutcomes,
  };

  return {
    ranAt: new Date().toISOString(),
    guideSynced: true,
    guideError: null,
    notes,
    voice,
    explore,
    locations,
    answers,
    message: buildSummaryMessage(notes, voice, explore, locations, answers),
  };
}

// In-process lock: a single mobile app process, user-initiated sync only. If a
// second "Sync now" tap arrives while a sync is already running, it gets the same
// in-flight result instead of starting an independent, racing sync — this covers
// both notes and locations, since they run inside the same performSync() call.
let syncInFlight: Promise<SyncResult> | null = null;

export function isSyncing(): boolean {
  return syncInFlight !== null;
}

export function syncAll(db: SQLiteDatabase): Promise<SyncResult> {
  if (syncInFlight) {
    return syncInFlight;
  }
  const run = performSync(db).finally(() => {
    syncInFlight = null;
  });
  syncInFlight = run;
  return run;
}
