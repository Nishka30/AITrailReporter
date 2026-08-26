import { apiRequest } from './client';

/** Mirrors the backend's transcription state machine EXACTLY (see
 * backend/app/db/models/transcription.py) — this is a different state machine
 * from the mobile app's own SyncStatus ("did the server receive the audio?").
 * This answers "did AI processing turn the audio into text?" */
export type TranscriptionStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface TranscriptionResponse {
  id: string;
  submissionId: string;
  status: TranscriptionStatus;
  transcript: string | null;
  languageCode: string | null;
  errorMessage: string | null;
}

interface TranscriptionResponseWire {
  id: string;
  submission_id: string;
  status: string;
  transcript: string | null;
  language_code: string | null;
  error_message: string | null;
}

function fromWire(wire: TranscriptionResponseWire): TranscriptionResponse {
  return {
    id: wire.id,
    submissionId: wire.submission_id,
    status: wire.status as TranscriptionStatus,
    transcript: wire.transcript,
    languageCode: wire.language_code,
    errorMessage: wire.error_message,
  };
}

/**
 * POST /api/v1/submissions/{submissionId}/transcribe. Starts transcription if
 * none is running yet, or simply reports the current state (without a second
 * provider call) if one is already 'processing' or already 'completed' — see
 * backend/README.md. Always resolves with the current true state; never
 * fabricates a transcript.
 */
export async function triggerTranscription(submissionId: string): Promise<TranscriptionResponse> {
  const wire = await apiRequest<TranscriptionResponseWire>(
    `/api/v1/submissions/${submissionId}/transcribe`,
    { method: 'POST' }
  );
  return fromWire(wire);
}
