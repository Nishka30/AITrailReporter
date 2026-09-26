import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, MapPin } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';

import { getPlaceDetail } from '../api/admin';
import type { PlaceKnowledgeCoverageDetail } from '../api/types';
import ObservationCard from '../components/review/ObservationCard';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';

/** Label + tone for the PRIMARY (category-driven) coverage state -- see
 * services/category_knowledge.py for where these four states come from.
 * Deliberately not the same visual weight as a moderation/urgent state:
 * this is a status readout, not an alert. */
const COVERAGE_STATE_STYLE: Record<
  PlaceKnowledgeCoverageDetail['state'],
  { label: string; className: string }
> = {
  fresh: { label: 'Fresh', className: 'bg-ok-soft text-ok-deep' },
  partially_stale: { label: 'Partially stale', className: 'bg-marigold-soft text-marigold-deep' },
  stale: { label: 'Stale', className: 'bg-fix-soft text-fix' },
  missing: { label: 'Missing', className: 'bg-paper-elevated text-ink-faint' },
};

function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString() : '—';
}

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
      {data.categories.length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {data.categories.map((c) => (
            <span
              key={`${c.kind}:${c.slug}`}
              className={`rounded-full px-2 py-0.5 text-xs ${
                c.is_primary ? 'bg-marigold-soft font-bold text-marigold-deep' : 'bg-paper-elevated text-ink-soft'
              }`}
              title={`${c.kind === 'place_type' ? 'Place type' : 'Theme'} · relevance ${c.relevance} · ${c.source}`}
            >
              {c.display_name}
            </span>
          ))}
        </div>
      ) : data.category ? (
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

      <h2 className="mb-3 font-heading text-base font-bold text-ink">Knowledge coverage</h2>
      {data.knowledge_coverage.length === 0 ? (
        <EmptyState title="No categories above the coverage threshold for this place yet" />
      ) : (
        <div className="mb-6 overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-paper-elevated text-ink-faint">
              <tr>
                <th className="px-3 py-2 font-bold">Category</th>
                <th className="px-3 py-2 font-bold">State</th>
                <th className="px-3 py-2 font-bold">Last verified</th>
                <th className="px-3 py-2 font-bold">Next stale</th>
                <th className="px-3 py-2 font-bold">Verified items</th>
              </tr>
            </thead>
            <tbody>
              {data.knowledge_coverage.map((cov) => {
                const style = COVERAGE_STATE_STYLE[cov.state];
                return (
                  <tr key={cov.category_assignment_id} className="border-t border-border">
                    <td className="px-3 py-2 text-ink">
                      {cov.display_name}
                      {cov.is_primary ? (
                        <span className="ml-1 text-xs text-ink-faint">(primary)</span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${style.className}`}>
                        {style.label}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-ink-soft">{formatDate(cov.last_verified_at)}</td>
                    <td className="px-3 py-2 text-ink-soft">{formatDate(cov.next_stale_at)}</td>
                    <td className="px-3 py-2 text-ink-soft">{cov.verified_item_count}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

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
