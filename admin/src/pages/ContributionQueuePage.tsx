import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import { getContributionQueue } from '../api/admin';
import ContributionCard from '../components/contributions/ContributionCard';
import PageHeader from '../components/layout/PageHeader';
import Pagination from '../components/ui/Pagination';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';

const SUBMISSION_TYPES = ['explore', 'memory', 'answer'];

/**
 * Contributions awaiting a PAYMENT decision. Deliberately a separate page
 * from the Content Review Queue (which reviews extracted knowledge facts,
 * not contributions) -- see backend/app/db/models/submission_review.py. Not
 * built on the shared ObservationListView: the filter set genuinely differs
 * (no knowledge_type/safety_critical/sort-by-confidence here), so a new,
 * small, purpose-built list view is clearer than bending a component built
 * for a different shape of data.
 */
export default function ContributionQueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const status = searchParams.get('status') ?? 'pending_review';
  const submissionType = searchParams.get('submission_type') ?? '';
  const q = searchParams.get('q') ?? '';
  const page = Number(searchParams.get('page') ?? '1');

  const filters = {
    status: status || undefined,
    submission_type: submissionType || undefined,
    q: q || undefined,
    page,
    page_size: 20,
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['contribution-queue', filters],
    queryFn: () => getContributionQueue(filters),
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== 'page') next.delete('page');
    setSearchParams(next);
  };

  return (
    <div>
      <PageHeader
        title="Payout Review"
        description="Decide whether a guide gets paid for what they submitted. No reward is granted until you approve it here."
      />

      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-paper-elevated p-3">
        <div className="flex items-center gap-2 rounded-lg border border-border bg-paper px-3 py-1.5">
          <Search className="h-4 w-4 text-ink-faint" />
          <input
            value={q}
            onChange={(e) => setParam('q', e.target.value)}
            placeholder="Search contribution text…"
            className="w-56 bg-transparent text-sm outline-none"
          />
        </div>

        <select
          value={status}
          onChange={(e) => setParam('status', e.target.value)}
          className="rounded-lg border border-border bg-paper px-3 py-1.5 text-sm"
        >
          <option value="pending_review">Pending review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="">All statuses</option>
        </select>

        <select
          value={submissionType}
          onChange={(e) => setParam('submission_type', e.target.value)}
          className="rounded-lg border border-border bg-paper px-3 py-1.5 text-sm"
        >
          <option value="">All types</option>
          {SUBMISSION_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? <LoadingState /> : null}
      {isError ? (
        <ErrorState message="Could not load the contribution queue." onRetry={() => refetch()} />
      ) : null}

      {data && data.items.length === 0 ? (
        <EmptyState
          title="Nothing here"
          description="No contributions currently match these filters."
        />
      ) : null}

      {data && data.items.length > 0 ? (
        <div className="space-y-3">
          {data.items.map((item) => (
            <ContributionCard key={item.submission_id} item={item} />
          ))}
          <Pagination
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            onPageChange={(p) => setParam('page', String(p))}
          />
        </div>
      ) : null}
    </div>
  );
}
