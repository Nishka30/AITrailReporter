import { File, UploadType } from 'expo-file-system';

import { API_BASE_URL, ApiError, NetworkError, extractDetailMessage } from './client';
import { submissionFromWire, type SubmissionResponse } from './submissions';

export interface UploadSubmissionAudioRequest {
  submissionId: string;
  /** Makes this call idempotent — see backend Submission.client_audio_id. A
   * DIFFERENT id from clientSubmissionId: it identifies the audio *attachment*
   * step specifically, not the submission itself. */
  clientAudioId: string;
  /** On-device file URI (e.g. from expo-audio's recorder.uri) — never read into
   * a JS string; the native uploader streams it straight from disk. */
  localUri: string;
  contentType: string;
  durationSeconds: number | null;
}

/**
 * POST /api/v1/submissions/{submissionId}/audio.
 *
 * Uses expo-file-system's NATIVE multipart uploader (`File#upload`, SDK 57's
 * current non-legacy API) rather than `fetch` + `FormData`. This is
 * deliberate, and was a bug fix: React Native's `fetch` accepts a
 * `{ uri, name, type }` pseudo-Blob in a FormData part, but on a real device
 * that path proved unreliable for on-disk file parts — it rejected with the
 * generic "Network request failed" *before* any bytes left the device, so
 * the request never appeared in the backend's logs at all, and the failure was
 * indistinguishable from a genuine connectivity problem (plain JSON requests
 * to the very same host succeeded throughout). The native uploader reads the
 * file with OkHttp/NSURLSession directly and reports real HTTP results, so a
 * failure here now means an actual network or server failure.
 *
 * The multipart body it builds matches the backend route exactly (see
 * backend/app/api/routes/submissions.py:upload_submission_audio):
 *   - `file`             — the recording, streamed from disk
 *   - `client_audio_id`  — form field
 *   - `duration_seconds` — form field, omitted when unknown (never faked)
 * The filename in the file part is the recording's real on-disk name, which
 * expo-audio's HIGH_QUALITY preset always gives a `.m4a` extension (see
 * src/audio/audioRecordingService.ts) — the extension the backend's
 * allow-list validates against.
 *
 * Idempotent on clientAudioId: retrying after a lost response returns the same
 * server state (200) instead of attaching a duplicate file. A 409 (ApiError with
 * status 409) means this submission already has DIFFERENT audio attached — a
 * real conflict.
 */
export async function uploadSubmissionAudio(
  req: UploadSubmissionAudioRequest
): Promise<SubmissionResponse> {
  const file = new File(req.localUri);
  if (!file.exists) {
    // Not a network problem — surfaced distinctly so it is never reported as
    // one (the whole point of the rewrite above). Retrying cannot fix this.
    throw new Error(
      'This recording is no longer on your device. It cannot be sent — record a new voice update instead.'
    );
  }

  // Only ever a string map — `duration_seconds` is omitted entirely rather than
  // sent as "null"/"0" when expo-audio could not report a duration.
  const parameters: Record<string, string> = { client_audio_id: req.clientAudioId };
  if (req.durationSeconds != null) {
    parameters.duration_seconds = String(req.durationSeconds);
  }

  let result: { body: string; status: number };
  try {
    result = await file.upload(`${API_BASE_URL}/api/v1/submissions/${req.submissionId}/audio`, {
      httpMethod: 'POST',
      uploadType: UploadType.MULTIPART,
      fieldName: 'file',
      mimeType: req.contentType,
      parameters,
    });
  } catch (err) {
    // A genuine transport failure now — the native uploader only rejects when
    // it truly could not complete the request.
    throw new NetworkError(err);
  }

  let payload: unknown = null;
  if (result.body) {
    try {
      payload = JSON.parse(result.body);
    } catch {
      payload = result.body;
    }
  }

  if (result.status < 200 || result.status >= 300) {
    throw new ApiError(
      result.status,
      extractDetailMessage(payload, `Request failed with status ${result.status}`),
      payload
    );
  }

  return submissionFromWire(payload as Parameters<typeof submissionFromWire>[0]);
}
