import type { SQLiteDatabase } from 'expo-sqlite';

import { getGuideSubmissionReviews } from '../api/submissionReviews';
import { getSetting, setSetting } from '../repositories/settingsRepository';
import { updateCaptureReviewStatus } from '../repositories/captureRepository';
import { updateAnswerReviewStatus } from '../repositories/answerRepository';

/**
 * Pulls admin-approval decisions for this guide's contributions (Step 19)
 * and writes them onto whichever local row each one belongs to.
 *
 * A row from the server is matched by `clientSubmissionId` against BOTH
 * local_capture.client_submission_id and local_answer.client_answer_id --
 * the server has no way to know which local table a given contribution came
 * from (it only ever sees ONE Submission either way), so this tries both
 * updates; exactly one of them ever matches a real row, the other is a
 * harmless no-op `UPDATE ... WHERE` that touches zero rows.
 *
 * Best-effort and non-blocking: a failure here (offline, backend hiccup)
 * must never stop the rest of sync, and never blocks a guide from
 * capturing/answering more. Callers should not await this inline with
 * user-facing "Sync now" feedback the way capture/answer sync is -- it is
 * informational, not something a submission's success depends on.
 */
export async function syncSubmissionReviews(
  db: SQLiteDatabase,
  serverGuideId: string
): Promise<{ checked: number; error: string | null }> {
  try {
    const since = await getSetting(db, 'submission_reviews_synced_at');
    const reviews = await getGuideSubmissionReviews(serverGuideId, since ?? undefined);

    for (const review of reviews) {
      await updateCaptureReviewStatus(
        db,
        review.clientSubmissionId,
        review.status,
        review.rejectionReason,
        review.rejectionNote,
        review.rewardPointsAwarded
      );
      await updateAnswerReviewStatus(
        db,
        review.clientSubmissionId,
        review.status,
        review.rejectionReason,
        review.rejectionNote,
        review.rewardPointsAwarded
      );
    }

    // Rows arrive newest-updated-first (see the backend route) -- the first
    // row's updatedAt is the newest we've now seen, so it becomes the floor
    // for next time. Only advanced when something was actually returned;
    // an empty response means "nothing changed since `since`", so the
    // existing floor is already correct and must not be reset to now() (a
    // decision made in the gap between "since" and "now" could then be
    // missed on the next poll).
    if (reviews.length > 0) {
      await setSetting(db, 'submission_reviews_synced_at', reviews[0].updatedAt);
    }

    return { checked: reviews.length, error: null };
  } catch (err) {
    return { checked: 0, error: err instanceof Error ? err.message : 'Could not check contribution status.' };
  }
}
