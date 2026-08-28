import { Check, RefreshCw, X } from 'lucide-react';
import { useState } from 'react';

import {
  approveObservation,
  changeObservationDecision,
  rejectObservation,
} from '../../api/admin';
import type { ObservationModeration, RejectionReason } from '../../api/types';
import DecisionDialog from './DecisionDialog';

/**
 * The one place approve/reject/change-decision are wired up. Mirrors the
 * backend's own separation exactly: approve/reject only ever act on a
 * pending_review observation; switching an already-decided one requires the
 * explicit "change decision" action below, never the same approve/reject
 * buttons (see backend/app/services/observation_moderation.py).
 */
export default function ModerationActions({
  observationId,
  moderation,
  onChanged,
}: {
  observationId: string;
  moderation: ObservationModeration;
  onChanged: (next: ObservationModeration) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<'reject' | 'change-to-rejected' | null>(null);

  const runAction = async (action: () => Promise<ObservationModeration>) => {
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

  if (moderation.status === 'pending_review') {
    return (
      <div>
        <div className="flex gap-2">
          <button
            disabled={busy}
            onClick={() => runAction(() => approveObservation(observationId))}
            className="flex items-center gap-2 rounded-full bg-ok px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            <Check className="h-4 w-4" /> Approve
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
            title="Reject this observation"
            confirmLabel="Reject"
            onClose={() => setDialog(null)}
            onConfirm={async (reason: RejectionReason, note: string) =>
              runAction(() => rejectObservation(observationId, reason, note || undefined))
            }
          />
        ) : null}
      </div>
    );
  }

  if (moderation.status === 'approved') {
    return (
      <div>
        <button
          disabled={busy}
          onClick={() => setDialog('change-to-rejected')}
          className="flex items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-bold text-ink-soft hover:bg-paper-muted disabled:opacity-50"
        >
          <RefreshCw className="h-4 w-4" /> Change decision to Rejected
        </button>
        {error ? <div className="mt-2 text-sm text-fix">{error}</div> : null}
        {dialog === 'change-to-rejected' ? (
          <DecisionDialog
            title="Change decision to Rejected"
            confirmLabel="Confirm change"
            onClose={() => setDialog(null)}
            onConfirm={async (reason: RejectionReason, note: string) =>
              runAction(() =>
                changeObservationDecision(observationId, 'rejected', reason, note || undefined)
              )
            }
          />
        ) : null}
      </div>
    );
  }

  // rejected
  return (
    <div>
      <button
        disabled={busy}
        onClick={() => runAction(() => changeObservationDecision(observationId, 'approved'))}
        className="flex items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-bold text-ink-soft hover:bg-paper-muted disabled:opacity-50"
      >
        <RefreshCw className="h-4 w-4" /> Change decision to Approved
      </button>
      {error ? <div className="mt-2 text-sm text-fix">{error}</div> : null}
    </div>
  );
}
