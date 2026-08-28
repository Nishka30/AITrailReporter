import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Phone, User } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';

import { getContributorDetail } from '../api/admin';
import ObservationCard from '../components/review/ObservationCard';
import StatCard from '../components/ui/StatCard';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';

export default function ContributorDetailPage() {
  const { guideId } = useParams<{ guideId: string }>();
  const navigate = useNavigate();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['contributor-detail', guideId],
    queryFn: () => getContributorDetail(guideId!),
    enabled: !!guideId,
  });

  if (isLoading) return <LoadingState />;
  if (isError || !data) return <ErrorState message="Could not load this contributor." onRetry={() => refetch()} />;

  return (
    <div>
      <button
        onClick={() => navigate(-1)}
        className="mb-4 flex items-center gap-1 text-sm font-bold text-ink-soft hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      <div className="mb-2 flex items-center gap-2">
        <User className="h-6 w-6 text-marigold" />
        <h1 className="font-heading text-2xl font-extrabold text-ink">{data.name}</h1>
        {!data.is_active ? <span className="text-sm text-ink-faint">(inactive)</span> : null}
      </div>
      {data.phone_number ? (
        <div className="mb-6 flex items-center gap-1 text-sm text-ink-soft">
          <Phone className="h-3.5 w-3.5" /> {data.phone_number}
        </div>
      ) : (
        <div className="mb-6" />
      )}

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Submissions" value={data.submission_count} />
        <StatCard label="Observations" value={data.observation_count} />
        <StatCard label="Approved" value={data.approved_count} />
        <StatCard label="Rejected" value={data.rejected_count} />
      </div>

      <h2 className="mb-3 font-heading text-base font-bold text-ink">Recent observations</h2>
      {data.recent_observations.length === 0 ? (
        <EmptyState title="No observations from this contributor yet" />
      ) : (
        <div className="space-y-3">
          {data.recent_observations.map((item) => (
            <ObservationCard key={item.observation_id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
