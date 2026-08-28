import { useQuery } from '@tanstack/react-query';
import { HelpCircle } from 'lucide-react';

import { getAdminQuestions } from '../api/admin';
import PageHeader from '../components/layout/PageHeader';
import StatusBadge from '../components/ui/StatusBadge';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';

const STATUS_TONE: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
  generated: 'success',
  processing: 'warning',
  pending: 'neutral',
  failed: 'danger',
};

export default function QuestionsPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin-questions'],
    queryFn: () => getAdminQuestions({}),
  });

  return (
    <div>
      <PageHeader
        title="Questions"
        description="Read-only visibility into the guide question/answer workflow -- generation and assignment are unchanged here."
      />

      {isLoading ? <LoadingState /> : null}
      {isError ? <ErrorState message="Could not load questions." onRetry={() => refetch()} /> : null}
      {data && data.length === 0 ? (
        <EmptyState title="No questions generated yet" icon={<HelpCircle className="h-8 w-8" />} />
      ) : null}

      {data && data.length > 0 ? (
        <div className="space-y-3">
          {data.map((q) => (
            <div key={q.question_id} className="rounded-lg border border-border bg-paper-elevated p-4 shadow-card">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-heading font-bold text-ink">{q.display_name}</div>
                <div className="flex items-center gap-2">
                  <StatusBadge label={q.gap_state} tone="neutral" />
                  <StatusBadge label={q.status} tone={STATUS_TONE[q.status] ?? 'neutral'} />
                </div>
              </div>
              {q.question_text ? <p className="mt-2 text-sm text-ink-soft">{q.question_text}</p> : null}
              <div className="mt-2 flex flex-wrap gap-4 text-xs text-ink-faint">
                <span>{q.nearest_known_place_name ?? 'Unknown place'}</span>
                <span>
                  {q.assignment_status
                    ? `${q.assignment_status} → ${q.assigned_guide_name}`
                    : 'Unassigned'}
                </span>
                <span>{new Date(q.created_at).toLocaleString()}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
