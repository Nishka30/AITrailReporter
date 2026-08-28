import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, MapPin } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';

import { getPlaceDetail } from '../api/admin';
import ObservationCard from '../components/review/ObservationCard';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';

export default function PlaceDetailPage() {
  const { locationId } = useParams<{ locationId: string }>();
  const navigate = useNavigate();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['place-detail', locationId],
    queryFn: () => getPlaceDetail(locationId!),
    enabled: !!locationId,
  });

  if (isLoading) return <LoadingState />;
  if (isError || !data) return <ErrorState message="Could not load this place." onRetry={() => refetch()} />;

  return (
    <div>
      <button
        onClick={() => navigate(-1)}
        className="mb-4 flex items-center gap-1 text-sm font-bold text-ink-soft hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      <div className="mb-6 flex items-center gap-2">
        <MapPin className="h-6 w-6 text-marigold" />
        <h1 className="font-heading text-2xl font-extrabold text-ink">{data.name}</h1>
      </div>
      {data.description ? <p className="mb-6 max-w-2xl text-sm text-ink-soft">{data.description}</p> : null}

      <h2 className="mb-3 font-heading text-base font-bold text-ink">Recent observations nearby</h2>
      {data.recent_observations.length === 0 ? (
        <EmptyState title="No observations reported near this place yet" />
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
