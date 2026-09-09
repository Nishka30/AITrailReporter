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

      <div className="mb-2 flex items-center gap-2">
        <MapPin className="h-6 w-6 text-marigold" />
        <h1 className="font-heading text-2xl font-extrabold text-ink">{data.name}</h1>
      </div>
      {data.category ? (
        <div className="mb-3 inline-block rounded-full bg-paper-elevated px-2 py-0.5 text-xs text-ink-soft">
          {data.category}
          {data.subcategory ? ` / ${data.subcategory}` : ''}
        </div>
      ) : null}
      {data.description ? <p className="mb-4 max-w-2xl text-sm text-ink-soft">{data.description}</p> : null}

      <dl className="mb-6 grid max-w-2xl grid-cols-2 gap-x-6 gap-y-1 rounded-lg border border-border bg-paper-elevated p-4 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-ink-faint">Coordinates</dt>
          <dd className="text-ink-soft">
            {data.latitude.toFixed(5)}, {data.longitude.toFixed(5)}
          </dd>
        </div>
        <div>
          <dt className="text-ink-faint">Source</dt>
          <dd className="text-ink-soft">{data.provider ?? data.source}</dd>
        </div>
        <div>
          <dt className="text-ink-faint">Discovered</dt>
          <dd className="text-ink-soft">{new Date(data.created_at).toLocaleDateString()}</dd>
        </div>
        {data.external_place_id ? (
          <div className="col-span-2 sm:col-span-3">
            <dt className="text-ink-faint">Place ID</dt>
            <dd className="break-all text-ink-soft">{data.external_place_id}</dd>
          </div>
        ) : null}
        {data.formatted_address ? (
          <div className="col-span-2 sm:col-span-3">
            <dt className="text-ink-faint">Address</dt>
            <dd className="text-ink-soft">{data.formatted_address}</dd>
          </div>
        ) : null}
      </dl>

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
