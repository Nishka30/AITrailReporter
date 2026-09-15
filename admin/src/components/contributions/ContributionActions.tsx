import { Check, X } from 'lucide-react';
import { useState } from 'react';

import { approveContribution, rejectContribution } from '../../api/admin';
import type { RejectionReason, SubmissionReview } from '../../api/types';
import DecisionDialog from '../review/DecisionDialog';

/**
 * Approve/reject for a contribution's PAYMENT decision. Deliberately has NO
 * "change decision" reversal, unlike ModerationActions -- once approved, the
 * guide has been paid (see backend/app/services/submission_review.py), and
 * this codebase has no reward-clawback mechanism anywhere. Once rejected, it
 * stays rejected. A decided contribution therefore renders as a plain,
 * read-only summary below.
 */
export default function ContributionActions({
  submissionId,
  review,
  onChanged,
}: {
  submissionId: string;
  review: SubmissionReview;
  onChanged: (next: SubmissionReview) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<'reject' | null>(null);

  const runAction = async (action: () => Promise<SubmissionReview>) => {
    setBusy(true);
    setError(null);
    try {
      onChanged(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setBusy(false);
    }
  };

  if (review.status === 'pending_review') {
    return (
      <div>
        <div className="flex gap-2">
          <button
            disabled={busy}
            onClick={() => runAction(() => approveContribution(submissionId))}
            className="flex items-center gap-2 rounded-full bg-ok px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            <Check className="h-4 w-4" /> Approve &amp; pay
          </button>
          <button
            disabled={busy}
            onClick={() => setDialog('reject')}
            className="flex items-center gap-2 rounded-full bg-fix px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            <X className="h-4 w-4" /> Reject
          </button>
        </div>
        {error ? <div className="mt-2 text-sm text-fix">{error}</div> : null}
        {dialog === 'reject' ? (
          <DecisionDialog
            title="Reject this contribution"
            confirmLabel="Reject"
            onClose={() => setDialog(null)}
            onConfirm={async (reason: RejectionReason, note: string) =>
              runAction(() => rejectContribution(submissionId, reason, note || undefined))
            }
          />
        ) : null}
      </div>
    );
  }

  // approved or rejected: final, no reversal path (see this component's docstring).
  return null;
}
