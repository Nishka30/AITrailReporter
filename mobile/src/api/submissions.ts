import type { DatePrecision, DateSource, LocationSource } from '../types/models';
import { apiRequest } from './client';

export interface CreateSubmissionRequest {
  guideId: string;
  /** Makes this call idempotent — see backend Submission.client_submission_id. */
  clientSubmissionId: string;
  captureType: 'note' | 'voice' | 'explore' | 'memory';
  /** Required for 'note' and 'explore'. Must be null for 'voice' — the backend
   * rejects a 'voice' submission that supplies text_content (its content is the
   * audio, uploaded separately — see api/audio.ts). An 'explore'/'memory'
   * contribution's photo, when present, is likewise uploaded separately (see
   * api/photos.ts), but its text is always carried here. */
  textContent: string | null;
  /** ISO-8601, timezone-aware — when the device captured this, not when it's sent. */
  submittedAt: string;
  /**
   * Set when this contribution answers a location-specific place question —
   * the "you're here right now" invitations the backend researched for the
   * place the guide is standing at. Only valid with captureType 'explore'.
   *
   * It is what makes the backend pay this at the question's own kind-specific
   * rate (a photo request is worth more than a status check) instead of the
   * generic Explore rate. The app never sends a point value — only which
   * question was answered.
   */
  sourcePlaceQuestionId?: string | null;

  // --- Location/date provenance -----------------------------------------
  // All optional and independent — sent as-is, whatever
  // src/location/photoLocationResolver.ts (or a plain live GPS read)
  // determined on-device. Never fabricated here to fill a gap; see
  // backend/app/schemas/submission.py for how an absent field is defaulted
  // server-side instead.
  latitude?: number | null;
  longitude?: number | null;
  locationSource?: LocationSource;
  locationAccuracyMeters?: number | null;
  locationCapturedAt?: string | null;
  locationLabel?: string | null;
  locationEvidence?: string | null;
  occurredAt?: string | null;
  occurredAtPrecision?: DatePrecision;
  dateSource?: DateSource;
}

export interface SubmissionAudioResponse {
  contentType: string;
  originalFilename: string;
  sizeBytes: number;
  durationSeconds: number | null;
}

/** Photo metadata for an 'explore' submission (Step 16). No duration field —
 * a photo has none, and the backend deliberately does not fabricate a shared
 * shape across the two media kinds. */
export interface SubmissionPhotoResponse {
  contentType: string;
  originalFilename: string;
  sizeBytes: number;
}

export interface SubmissionResponse {
  id: string;
  guideId: string;
  clientSubmissionId: string | null;
  submissionType: string;
  rawText: string | null;
  status: string;
  submittedAt: string;
  createdAt: string;
  updatedAt: string;
  /** Null until audio has actually been uploaded for a 'voice' submission. */
  audio: SubmissionAudioResponse | null;
  /** Null until a photo has actually been uploaded for an 'explore' submission. */
  photo: SubmissionPhotoResponse | null;
}

interface SubmissionAudioResponseWire {
  content_type: string;
  original_filename: string;
  size_bytes: number;
  duration_seconds: number | null;
}

interface SubmissionResponseWire {
  id: string;
  guide_id: string;
  client_submission_id: string | null;
  submission_type: string;
  raw_text: string | null;
  status: string;
  submitted_at: string;
  created_at: string;
  updated_at: string;
  audio: SubmissionAudioResponseWire | null;
  photo: SubmissionPhotoResponseWire | null;
}

interface SubmissionPhotoResponseWire {
  content_type: string;
  original_filename: string;
  size_bytes: number;
}

export function submissionFromWire(wire: SubmissionResponseWire): SubmissionResponse {
  return {
    id: wire.id,
    guideId: wire.guide_id,
    clientSubmissionId: wire.client_submission_id,
    submissionType: wire.submission_type,
    rawText: wire.raw_text,
    status: wire.status,
    submittedAt: wire.submitted_at,
    createdAt: wire.created_at,
    updatedAt: wire.updated_at,
    audio: wire.audio
      ? {
          contentType: wire.audio.content_type,
          originalFilename: wire.audio.original_filename,
          sizeBytes: wire.audio.size_bytes,
          durationSeconds: wire.audio.duration_seconds,
        }
      : null,
    // `?? null` rather than a bare ternary: a backend that predates Step 16
    // omits this key entirely, and `undefined` would violate the declared
    // `| null` contract for every consumer.
    photo: wire.photo
      ? {
          contentType: wire.photo.content_type,
          originalFilename: wire.photo.original_filename,
          sizeBytes: wire.photo.size_bytes,
        }
      : null,
  };
}

/**
 * POST /api/v1/submissions. Idempotent on clientSubmissionId: calling this again
 * with the same clientSubmissionId and the same payload returns the same server
 * submission instead of creating another. A 409 (ApiError with status 409) means
 * the same clientSubmissionId was already used for different data — a real
 * conflict, not something a plain retry will resolve.
 */
export async function createOrGetSubmission(
  req: CreateSubmissionRequest
): Promise<SubmissionResponse> {
  const wire = await apiRequest<SubmissionResponseWire>('/api/v1/submissions', {
    method: 'POST',
    body: {
      guide_id: req.guideId,
      client_submission_id: req.clientSubmissionId,
      capture_type: req.captureType,
      text_content: req.textContent,
      submitted_at: req.submittedAt,
      source_place_question_id: req.sourcePlaceQuestionId ?? null,
      latitude: req.latitude ?? null,
      longitude: req.longitude ?? null,
      location_source: req.locationSource ?? null,
      location_accuracy_meters: req.locationAccuracyMeters ?? null,
      location_captured_at: req.locationCapturedAt ?? null,
      location_label: req.locationLabel ?? null,
      location_evidence: req.locationEvidence ?? null,
      occurred_at: req.occurredAt ?? null,
      occurred_at_precision: req.occurredAtPrecision ?? null,
      date_source: req.dateSource ?? null,
    },
  });
  return submissionFromWire(wire);
}
