import { useQuery } from '@tanstack/react-query';
import { Users } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';

import { getContributors } from '../api/admin';
import PageHeader from '../components/layout/PageHeader';
import Pagination from '../components/ui/Pagination';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';

export default function ContributorsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const page = Number(searchParams.get('page') ?? '1');

  const filters = {
    page,
    page_size: 20,
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin-contributors', filters],
    queryFn: () => getContributors(filters),
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
      <PageHeader title="Guides" description="Guides who have submitted field reports." />

      {isLoading ? <LoadingState /> : null}
      {isError ? <ErrorState message="Could not load contributors." onRetry={() => refetch()} /> : null}
      {data && data.items.length === 0 ? <EmptyState title="No guides yet" icon={<Users className="h-8 w-8" />} /> : null}

      {data && data.items.length > 0 ? (
        <div>
          <div className="overflow-hidden rounded-lg border border-border bg-paper-elevated shadow-card">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border bg-paper-muted text-xs font-bold uppercase text-ink-faint">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Submissions</th>
                  <th className="px-4 py-3">Observations</th>
                  <th className="px-4 py-3">Pending</th>
                  <th className="px-4 py-3">Approved</th>
                  <th className="px-4 py-3">Rejected</th>
                  <th className="px-4 py-3">Last active</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.guide_id} className="border-b border-border last:border-0 hover:bg-paper-muted">
                    <td className="px-4 py-3">
                      <Link to={`/contributors/${c.guide_id}`} className="font-bold text-ink hover:text-marigold-deep">
                        {c.name}
                      </Link>
                      {!c.is_active ? <span className="ml-2 text-xs text-ink-faint">(inactive)</span> : null}
                    </td>
                    <td className="px-4 py-3">{c.submission_count}</td>
                    <td className="px-4 py-3">{c.observation_count}</td>
                    <td className="px-4 py-3">{c.pending_review_count}</td>
                    <td className="px-4 py-3">{c.approved_count}</td>
                    <td className="px-4 py-3">{c.rejected_count}</td>
                    <td className="px-4 py-3 text-ink-faint">
                      {c.last_active_at ? new Date(c.last_active_at).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
