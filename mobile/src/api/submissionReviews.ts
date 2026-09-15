import type { SubmissionReviewStatus } from '../types/models';
import { apiRequest } from './client';

/**
 * Admin-approval status for a guide's own contributions (Step 19).
 *
 * THE APP HOLDS NO REWARD DECISIONS OF ITS OWN, same discipline as
 * api/rewards.ts: a contribution is 'pending_review' until an admin decides
 * otherwise, and this app never shows a reward as earned before that
 * happens. Matched back to a local capture/answer by `clientSubmissionId` --
 * the SAME id this device already generated at submission time (see
 * captureRepository.ts / local_answer.clientAnswerId), never a server-minted
 * one the app would have to learn separately.
 */

export interface GuideSubmissionReview {
  submissionId: string;
  clientSubmissionId: string;
  submissionType: string;
  status: SubmissionReviewStatus;
  rejectionReason: string | null;
  rejectionNote: string | null;
  /** Present only once status === 'approved'. Never display a reward as
   * earned while this is null. */
  rewardPointsAwarded: number | null;
  updatedAt: string;
}

interface GuideSubmissionReviewWire {
  submission_id: string;
  client_submission_id: string;
  submission_type: string;
  status: SubmissionReviewStatus;
  rejection_reason: string | null;
  rejection_note: string | null;
  reward_points_awarded: number | null;
  updated_at: string;
}

function fromWire(w: GuideSubmissionReviewWire): GuideSubmissionReview {
  return {
    submissionId: w.submission_id,
    clientSubmissionId: w.client_submission_id,
    submissionType: w.submission_type,
    status: w.status,
    rejectionReason: w.rejection_reason,
    rejectionNote: w.rejection_note,
    rewardPointsAwarded: w.reward_points_awarded,
    updatedAt: w.updated_at,
  };
}

/** GET /api/v1/guides/{guideId}/submission-reviews -- what this screen polls
 * to learn whether a contribution it already knows about locally has moved
 * from pending to approved/rejected. `since` narrows the response to rows
 * updated after a previous poll's newest `updatedAt`, purely as a bandwidth
 * optimization -- the caller still matches every returned row by
 * clientSubmissionId, never by position or count. */
export async function getGuideSubmissionReviews(
  guideId: string,
  since?: string
): Promise<GuideSubmissionReview[]> {
  const query = since ? `?since=${encodeURIComponent(since)}` : '';
  const wire = await apiRequest<GuideSubmissionReviewWire[]>(
    `/api/v1/guides/${guideId}/submission-reviews${query}`
  );
  return wire.map(fromWire);
}
