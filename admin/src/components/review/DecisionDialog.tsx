import { useState } from 'react';

import type { RejectionReason } from '../../api/types';

const REASONS: { value: RejectionReason; label: string }[] = [
  { value: 'inaccurate', label: 'Inaccurate' },
  { value: 'unsafe', label: 'Unsafe' },
  { value: 'duplicate', label: 'Duplicate' },
  { value: 'poor_quality', label: 'Poor quality' },
  { value: 'not_useful', label: 'Not useful' },
  { value: 'other', label: 'Other' },
];

/**
 * Used for two flows that both need a rejection reason: rejecting a
 * pending_review observation, and switching an already-decided observation
 * TO rejected via change-decision (see backend's separate change-decision
 * endpoint -- reversing a prior decision is deliberately its own action, not
 * something approve/reject do silently).
 */
export default function DecisionDialog({
  title,
  confirmLabel,
  onConfirm,
  onClose,
}: {
  title: string;
  confirmLabel: string;
  onConfirm: (reason: RejectionReason, note: string) => Promise<void>;
  onClose: () => void;
}) {
  const [reason, setReason] = useState<RejectionReason>('inaccurate');
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm(reason, note.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-6" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-lg bg-paper-elevated p-6 shadow-card"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="font-heading text-lg font-bold text-ink">{title}</h2>

        <div className="mt-4 space-y-2">
          <span className="text-sm font-bold text-ink-soft">Reason</span>
          <div className="grid grid-cols-2 gap-2">
            {REASONS.map((r) => (
              <button
                key={r.value}
                onClick={() => setReason(r.value)}
                className={`rounded-lg border px-3 py-2 text-sm font-bold transition-colors ${
                  reason === r.value
                    ? 'border-marigold bg-marigold-soft text-marigold-deep'
                    : 'border-border text-ink-soft hover:bg-paper-muted'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4">
          <label className="text-sm font-bold text-ink-soft" htmlFor="decision-note">
            Note {reason === 'other' ? '(required)' : '(optional)'}
          </label>
          <textarea
            id="decision-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            className="mt-1 w-full rounded-lg border border-border bg-paper p-2 text-sm"
            placeholder="Add context for this decision…"
          />
        </div>

        {error ? <div className="mt-3 text-sm text-fix">{error}</div> : null}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-full border border-border px-4 py-2 text-sm font-bold text-ink-soft"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || (reason === 'other' && !note.trim())}
            className="rounded-full bg-fix px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {submitting ? 'Saving…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
