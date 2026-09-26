import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { getKnowledgeConflicts, resolveKnowledgeConflict } from '../api/admin';
import type { CategoryKnowledgeConflict, VolatilityClass } from '../api/types';
import { VOLATILITY_CLASSES } from '../api/types';
import PageHeader from '../components/layout/PageHeader';
import StatusBadge from '../components/ui/StatusBadge';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';

/** One conflict's resolve controls -- local state only lives here so
 * switching between conflicts never leaks a draft replacement-text into the
 * wrong row. */
function ConflictCard({ conflict }: { conflict: CategoryKnowledgeConflict }) {
  const queryClient = useQueryClient();
  const [replacementText, setReplacementText] = useState(conflict.new_answer_text);
  // Defaults to the EXISTING knowledge item's own volatility -- the Admin
  // may change it before confirming, but never supplies a raw duration: the
  // backend alone maps this class to freshness_duration_hours (see
  // category_knowledge_policy.resolve_freshness_duration_hours).
  const [volatility, setVolatility] = useState<VolatilityClass>(conflict.existing_volatility);

  const resolve = useMutation({
    mutationFn: (resolution: 'confirmed' | 'superseded' | 'dismissed') =>
      resolveKnowledgeConflict(
        conflict.id,
        resolution,
        replacementText,
        resolution === 'superseded' ? volatility : undefined
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge-conflicts'] });
    },
  });

  return (
    <div className="rounded-lg border border-border bg-paper-elevated p-4 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link
          to={`/places/${conflict.location_id}`}
          className="font-heading font-bold text-ink hover:underline"
        >
          {conflict.location_name}
        </Link>
        <StatusBadge label={conflict.category_display_name} tone="info" />
      </div>

      <dl className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs font-bold uppercase text-ink-faint">Existing knowledge</dt>
          <dd className="mt-1 rounded-lg bg-paper-muted p-2 text-ink">{conflict.existing_knowledge_text}</dd>
        </div>
        <div>
          <dt className="text-xs font-bold uppercase text-ink-faint">New guide answer</dt>
          <dd className="mt-1 rounded-lg bg-paper-muted p-2 text-ink">{conflict.new_answer_text}</dd>
        </div>
      </dl>

      <div className="mt-3 text-xs text-ink-faint">
        Reported {new Date(conflict.created_at).toLocaleString()}
      </div>

      {conflict.status === 'resolved' ? (
        <div className="mt-3 text-sm text-ink-soft">
          Resolved as <span className="font-bold">{conflict.resolution}</span> by{' '}
          {conflict.resolved_by} on{' '}
          {conflict.resolved_at ? new Date(conflict.resolved_at).toLocaleString() : '—'}
        </div>
      ) : (
        <div className="mt-4 space-y-2 border-t border-border pt-3">
          <label className="block text-xs font-bold uppercase text-ink-faint">
            Replacement knowledge text (used only if you choose "Supersede")
          </label>
          <textarea
            value={replacementText}
            onChange={(e) => setReplacementText(e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-border bg-paper p-2 text-sm text-ink"
          />

          <label className="block text-xs font-bold uppercase text-ink-faint">
            Volatility for the replacement (used only if you choose "Supersede")
          </label>
          <select
            value={volatility}
            onChange={(e) => setVolatility(e.target.value as VolatilityClass)}
            className="w-full rounded-lg border border-border bg-paper p-2 text-sm text-ink"
          >
            {VOLATILITY_CLASSES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => resolve.mutate('confirmed')}
              disabled={resolve.isPending}
              className="rounded-full bg-ok-soft px-3 py-1.5 text-xs font-bold text-ok-deep disabled:opacity-50"
            >
              Confirm existing knowledge
            </button>
            <button
              onClick={() => resolve.mutate('superseded')}
              disabled={resolve.isPending || !replacementText.trim()}
              className="rounded-full bg-marigold px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50"
            >
              Supersede with replacement
            </button>
            <button
              onClick={() => resolve.mutate('dismissed')}
              disabled={resolve.isPending}
              className="rounded-full bg-paper-muted px-3 py-1.5 text-xs font-bold text-ink-soft disabled:opacity-50"
            >
              Dismiss (not real evidence)
            </button>
          </div>
          {resolve.isError ? (
            <p className="text-xs text-fix">Could not save that decision. Try again.</p>
          ) : null}
        </div>
      )}
    </div>
  );
}

export default function KnowledgeConflictsPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['knowledge-conflicts', 'open'],
    queryFn: () => getKnowledgeConflicts('open'),
  });

  return (
    <div>
      <PageHeader
        title="Knowledge Conflicts"
        description='Re-verifications whose relationship to existing, trusted knowledge could not be confidently classified as CONFIRMS or CONTRADICTS -- the standing knowledge is left untouched until you resolve one.'
      />

      {isLoading ? <LoadingState /> : null}
      {isError ? <ErrorState message="Could not load knowledge conflicts." onRetry={() => refetch()} /> : null}
      {data && data.length === 0 ? (
        <EmptyState title="No open knowledge conflicts" icon={<ShieldAlert className="h-8 w-8" />} />
      ) : null}

      {data && data.length > 0 ? (
        <div className="space-y-3">
          {data.map((conflict) => (
            <ConflictCard key={conflict.id} conflict={conflict} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
