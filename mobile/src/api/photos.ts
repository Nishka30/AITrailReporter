import { File, UploadType } from 'expo-file-system';

import { API_BASE_URL, ApiError, NetworkError, extractDetailMessage } from './client';
import { submissionFromWire, type SubmissionResponse } from './submissions';

export interface UploadSubmissionPhotoRequest {
  submissionId: string;
  /** Makes this call idempotent — see backend Submission.client_photo_id. A
   * THIRD distinct id from clientSubmissionId and clientAudioId: it identifies
   * the photo *attachment* step specifically. */
  clientPhotoId: string;
  /** On-device file URI, already copied into app-owned storage by
   * src/photo/photoPickerService.ts — never read into a JS string; the native
   * uploader streams it straight from disk. */
  localUri: string;
  contentType: string;
}

/**
 * POST /api/v1/submissions/{submissionId}/photo.
 *
 * Uses expo-file-system's NATIVE multipart uploader (`File#upload`) for the
 * same hard-won reason api/audio.ts does — React Native's `fetch` + `FormData`
 * proved unreliable for on-disk file parts on a real device, failing with a
 * generic "Network request failed" BEFORE any bytes left the phone, which was
 * indistinguishable from a genuine connectivity problem. See api/audio.ts's
 * header for the full history. Reusing that proven path here rather than
 * rediscovering the same bug.
 *
 * The multipart body matches the backend route exactly (see
 * backend/app/api/routes/submissions.py:upload_submission_photo):
 *   - `file`            — the image, streamed from disk
 *   - `client_photo_id` — form field
 *
 * Idempotent on clientPhotoId: retrying after a lost response returns the same
 * server state (200) instead of storing a duplicate file. A 409 means this
 * submission already has a DIFFERENT photo attached — a real conflict that a
 * plain retry cannot fix.
 */
export async function uploadSubmissionPhoto(
  req: UploadSubmissionPhotoRequest
): Promise<SubmissionResponse> {
  const file = new File(req.localUri);
  if (!file.exists) {
    // Not a network problem — surfaced distinctly so it is never reported as
    // one. Retrying cannot fix this.
    throw new Error(
      'This photo is no longer on your device. It cannot be sent — add the photo again.'
    );
  }

  let result: { body: string; status: number };
  try {
    result = await file.upload(`${API_BASE_URL}/api/v1/submissions/${req.submissionId}/photo`, {
      httpMethod: 'POST',
      uploadType: UploadType.MULTIPART,
      fieldName: 'file',
      mimeType: req.contentType,
      parameters: { client_photo_id: req.clientPhotoId },
    });
  } catch (err) {
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
