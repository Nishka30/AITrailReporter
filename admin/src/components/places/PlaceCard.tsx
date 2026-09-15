import { MapPin } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { PlaceSummary } from '../../api/types';

const MAX_VISIBLE_CATEGORIES = 3;

/** One Location card for the Places grid. Category chips come from the real
 * multi-category assignment (see PlaceSummary.categories) -- the primary
 * place_type first (if any), then whatever else is most relevant, with
 * anything beyond MAX_VISIBLE_CATEGORIES collapsed into a "+N" chip rather
 * than cluttering the card. Falls back to the legacy category/subcategory
 * pair only if a place genuinely has no multi-category assignment yet. */
export default function PlaceCard({ place }: { place: PlaceSummary }) {
  const primary = place.categories.find((c) => c.is_primary && c.kind === 'place_type');
  const rest = place.categories.filter((c) => c !== primary);
  const ordered = primary ? [primary, ...rest] : place.categories;
  const visible = ordered.slice(0, MAX_VISIBLE_CATEGORIES);
  const overflowCount = ordered.length - visible.length;

  return (
    <Link
      to={`/places/${place.location_id}`}
      className="flex flex-col rounded-lg border border-border bg-paper-elevated p-4 shadow-card hover:shadow-md"
    >
      <div className="flex items-center gap-2 font-heading font-bold text-ink">
        <MapPin className="h-4 w-4 shrink-0 text-marigold" />
        <span className="truncate">{place.name}</span>
      </div>

      {visible.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {visible.map((c) => (
            <span
              key={`${c.kind}:${c.slug}`}
              className="rounded-full bg-paper px-2 py-0.5 text-xs text-ink-soft"
            >
              {c.display_name}
            </span>
          ))}
          {overflowCount > 0 ? (
            <span className="rounded-full bg-paper px-2 py-0.5 text-xs text-ink-faint">
              +{overflowCount}
            </span>
          ) : null}
        </div>
      ) : place.category ? (
        <div className="mt-2 inline-block w-fit rounded-full bg-paper px-2 py-0.5 text-xs text-ink-soft">
          {place.category}
          {place.subcategory ? ` / ${place.subcategory}` : ''}
        </div>
      ) : null}

      <div className="mt-3 flex gap-4 text-sm text-ink-soft">
        <span>{place.nearby_observation_count} nearby</span>
        <span>{place.pending_review_count} pending</span>
        <span>{place.approved_count} approved</span>
      </div>
    </Link>
  );
}
