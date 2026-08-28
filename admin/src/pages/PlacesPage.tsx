import { useQuery } from '@tanstack/react-query';
import { MapPin } from 'lucide-react';
import { Link } from 'react-router-dom';

import { getPlaces } from '../api/admin';
import PageHeader from '../components/layout/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';

export default function PlacesPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin-places'],
    queryFn: getPlaces,
  });

  return (
    <div>
      <PageHeader title="Places" description="Known places, and how much has been reported nearby." />

      {isLoading ? <LoadingState /> : null}
      {isError ? <ErrorState message="Could not load places." onRetry={() => refetch()} /> : null}
      {data && data.length === 0 ? (
        <EmptyState title="No known places yet" icon={<MapPin className="h-8 w-8" />} />
      ) : null}

      {data && data.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((place) => (
            <Link
              key={place.location_id}
              to={`/places/${place.location_id}`}
              className="rounded-lg border border-border bg-paper-elevated p-4 shadow-card hover:shadow-md"
            >
              <div className="flex items-center gap-2 font-heading font-bold text-ink">
                <MapPin className="h-4 w-4 text-marigold" /> {place.name}
              </div>
              <div className="mt-2 flex gap-4 text-sm text-ink-soft">
                <span>{place.nearby_observation_count} nearby</span>
                <span>{place.pending_review_count} pending</span>
                <span>{place.approved_count} approved</span>
              </div>
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
