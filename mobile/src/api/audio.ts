import { API_BASE_URL, ApiError, NetworkError, extractDetailMessage } from './client';
import { submissionFromWire, type SubmissionResponse } from './submissions';

export interface UploadSubmissionAudioRequest {
  submissionId: string;
  /** Makes this call idempotent — see backend Submission.client_audio_id. A
   * DIFFERENT id from clientSubmissionId: it identifies the audio *attachment*
   * step specifically, not the submission itself. */
  clientAudioId: string;
  /** On-device file URI (e.g. from expo-audio's recorder.uri) — never read into
   * a JS string; handed to fetch()/FormData as a file reference. */
  localUri: string;
  contentType: string;
  filename: string;
  durationSeconds: number | null;
}

/**
 * POST /api/v1/submissions/{submissionId}/audio. Does NOT go through
 * apiRequest() (src/api/client.ts) — that helper always sends
 * `Content-Type: application/json` and JSON-encodes the body, which is wrong for
 * a multipart file upload (the browser/RN runtime must set the multipart
 * boundary itself). This is the one deliberate exception to "everything goes
 * through apiRequest()"; it still reuses the same ApiError/NetworkError/base-URL
 * conventions so callers handle errors identically either way.
 *
 * Idempotent on clientAudioId: retrying after a lost response returns the same
 * server state (200) instead of attaching a duplicate file. A 409 (ApiError with
 * status 409) means this submission already has DIFFERENT audio attached — a
 * real conflict.
 */
export async function uploadSubmissionAudio(
  req: UploadSubmissionAudioRequest
): Promise<SubmissionResponse> {
  const form = new FormData();
  // React Native's fetch/FormData accepts this {uri,name,type} shape directly —
  // it streams the file from disk, it is never read into a JS string.
  form.append('file', {
    uri: req.localUri,
    name: req.filename,
    type: req.contentType,
  } as unknown as Blob);
  form.append('client_audio_id', req.clientAudioId);
  if (req.durationSeconds != null) {
    form.append('duration_seconds', String(req.durationSeconds));
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/submissions/${req.submissionId}/audio`, {
      method: 'POST',
      body: form,
      // No explicit Content-Type: the runtime must set it (including the
      // multipart boundary) itself — setting it manually breaks the upload.
    });
  } catch (err) {
    throw new NetworkError(err);
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extractDetailMessage(payload, `Request failed with status ${response.status}`),
      payload
    );
  }

  return submissionFromWire(payload as Parameters<typeof submissionFromWire>[0]);
}
