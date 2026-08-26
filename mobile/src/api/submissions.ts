import { apiRequest } from './client';

export interface CreateSubmissionRequest {
  guideId: string;
  /** Makes this call idempotent — see backend Submission.client_submission_id. */
  clientSubmissionId: string;
  captureType: 'note' | 'voice';
  /** Required for 'note'. Must be null for 'voice' — the backend rejects a
   * 'voice' submission that supplies text_content (its content is the audio,
   * uploaded separately — see api/audio.ts). */
  textContent: string | null;
  /** ISO-8601, timezone-aware — when the device captured this, not when it's sent. */
  submittedAt: string;
}

export interface SubmissionAudioResponse {
  contentType: string;
  originalFilename: string;
  sizeBytes: number;
  durationSeconds: number | null;
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
    },
  });
  return submissionFromWire(wire);
}
