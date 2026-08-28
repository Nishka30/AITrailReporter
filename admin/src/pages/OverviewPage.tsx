import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, Clock, Compass, HelpCircle, Map, Users, XCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { getOverview } from '../api/admin';
import PageHeader from '../components/layout/PageHeader';
import StatCard from '../components/ui/StatCard';
import { ErrorState, LoadingState } from '../components/ui/States';

export default function OverviewPage() {
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin-overview'],
    queryFn: getOverview,
  });

  return (
    <div>
      <PageHeader
        title="Overview"
        description="Real counts from the current database -- nothing here is estimated."
      />

      {isLoading ? <LoadingState /> : null}
      {isError ? <ErrorState message="Could not load the overview." onRetry={() => refetch()} /> : null}

      {data ? (
        <div className="space-y-6">
          <div>
            <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-ink-faint">
              Moderation
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <button className="text-left" onClick={() => navigate('/review-queue')}>
                <StatCard
                  label="Pending review"
                  value={data.pending_review_count}
                  icon={<Clock className="h-5 w-5" />}
                  tone={data.pending_review_count > 0 ? 'warning' : 'default'}
                />
              </button>
              <button
                className="text-left"
                onClick={() => navigate('/review-queue?safety_critical=true')}
              >
                <StatCard
                  label="Safety-critical pending"
                  value={data.safety_critical_pending_count}
                  icon={<AlertTriangle className="h-5 w-5" />}
                  tone={data.safety_critical_pending_count > 0 ? 'danger' : 'default'}
                />
              </button>
              <StatCard
                label="Approved"
                value={data.approved_count}
                icon={<CheckCircle2 className="h-5 w-5" />}
              />
              <StatCard label="Rejected" value={data.rejected_count} icon={<XCircle className="h-5 w-5" />} />
            </div>
          </div>

          <div>
            <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-ink-faint">
              Field activity
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Guides" value={data.total_guides} icon={<Users className="h-5 w-5" />} />
              <StatCard label="Submissions" value={data.total_submissions} icon={<Map className="h-5 w-5" />} />
              <StatCard
                label="Observations"
                value={data.total_observations}
                icon={<Compass className="h-5 w-5" />}
              />
              <StatCard
                label="Active knowledge types"
                value={data.active_knowledge_type_count}
                icon={<Compass className="h-5 w-5" />}
              />
            </div>
          </div>

          <div>
            <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-ink-faint">
              Questions
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Generated"
                value={data.questions_generated_count}
                icon={<HelpCircle className="h-5 w-5" />}
              />
              <StatCard
                label="Awaiting assignment"
                value={data.questions_pending_assignment_count}
                icon={<HelpCircle className="h-5 w-5" />}
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
