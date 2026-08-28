import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import type { ReviewQueueFilters, ReviewQueueResult } from '../../api/types';
import PageHeader from '../layout/PageHeader';
import Pagination from '../ui/Pagination';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import ObservationCard from './ObservationCard';

const SOURCE_TYPES = ['note', 'voice', 'explore', 'answer'];
const SORT_OPTIONS = [
  { value: 'created_at', label: 'Newest reviewed-in first' },
  { value: 'observed_at', label: 'Most recently observed first' },
  { value: 'confidence', label: 'Highest confidence first' },
];

/**
 * Shared list view behind both the Review Queue (defaults to
 * status=pending_review) and the Knowledge browser (defaults to all
 * statuses) -- same filters, same card, same pagination; only the default
 * status and page title differ. Filter state lives in the URL so a filtered
 * view is linkable/bookmarkable/back-button-safe.
 */
export default function ObservationListView({
  queryKey,
  fetchFn,
  title,
  description,
  defaultStatus,
  showStatusFilter,
}: {
  queryKey: string;
  fetchFn: (filters: ReviewQueueFilters) => Promise<ReviewQueueResult>;
  title: string;
  description: string;
  defaultStatus: string;
  showStatusFilter: boolean;
}) {
  const [searchParams, setSearchParams] = useSearchParams();

  const status = searchParams.get('status') ?? defaultStatus;
  const knowledgeType = searchParams.get('knowledge_type') ?? '';
  const safetyCritical = searchParams.get('safety_critical') ?? '';
  const sourceType = searchParams.get('source_type') ?? '';
  const q = searchParams.get('q') ?? '';
  const sort = searchParams.get('sort') ?? 'created_at';
  const page = Number(searchParams.get('page') ?? '1');

  const filters: ReviewQueueFilters = {
    status: status || undefined,
    knowledge_type: knowledgeType || undefined,
    safety_critical: safetyCritical ? safetyCritical === 'true' : undefined,
    source_type: sourceType || undefined,
    q: q || undefined,
    sort,
    page,
    page_size: 20,
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [queryKey, filters],
    queryFn: () => fetchFn(filters),
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
      <PageHeader title={title} description={description} />

      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-paper-elevated p-3">
        <div className="flex items-center gap-2 rounded-lg border border-border bg-paper px-3 py-1.5">
          <Search className="h-4 w-4 text-ink-faint" />
          <input
            value={q}
            onChange={(e) => setParam('q', e.target.value)}
            placeholder="Search evidence or text…"
            className="w-48 bg-transparent text-sm outline-none"
          />
        </div>

        {showStatusFilter ? (
          <select
            value={status}
            onChange={(e) => setParam('status', e.target.value)}
            className="rounded-lg border border-border bg-paper px-3 py-1.5 text-sm"
          >
            <option value="">All statuses</option>
            <option value="pending_review">Pending review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        ) : null}

        <input
          value={knowledgeType}
          onChange={(e) => setParam('knowledge_type', e.target.value)}
          placeholder="Knowledge type…"
          className="rounded-lg border border-border bg-paper px-3 py-1.5 text-sm"
        />

        <select
          value={sourceType}
          onChange={(e) => setParam('source_type', e.target.value)}
          className="rounded-lg border border-border bg-paper px-3 py-1.5 text-sm"
        >
          <option value="">All sources</option>
          {SOURCE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <label className="flex items-center gap-2 text-sm text-ink-soft">
          <input
            type="checkbox"
            checked={safetyCritical === 'true'}
            onChange={(e) => setParam('safety_critical', e.target.checked ? 'true' : '')}
          />
          Safety-critical only
        </label>

        <select
          value={sort}
          onChange={(e) => setParam('sort', e.target.value)}
          className="ml-auto rounded-lg border border-border bg-paper px-3 py-1.5 text-sm"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? <LoadingState /> : null}
      {isError ? <ErrorState message="Could not load observations." onRetry={() => refetch()} /> : null}

      {data && data.items.length === 0 ? (
        <EmptyState
          title="Nothing here"
          description="No observations currently match these filters."
        />
      ) : null}

      {data && data.items.length > 0 ? (
        <div className="space-y-3">
          {data.items.map((item) => (
            <ObservationCard key={item.observation_id} item={item} />
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
