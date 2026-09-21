import { MapPin } from 'lucide-react';
import { Link } from 'react-router-dom';

/**
 * THE single "where is this contribution" display, shared by every
 * contribution-facing page (Contribution Review, Content Review) so the
 * rule lives in exactly one place: a contribution's OWN stored
 * latitude/longitude is the authoritative answer, always -- a nearby known
 * Location is optional enrichment, shown separately, and NEVER substitutes
 * for or hides the coordinate.
 *
 * WHY THIS EXISTS: before this component, both detail pages rendered
 * "Location not specified" whenever no known Location fell within the
 * backend's ~500m radius of the contribution's coordinate -- even when that
 * coordinate was a real, valid, non-null value. A contribution reported from
 * genuinely unmapped ground (no nearby discovered POI) looked, to an admin,
 * indistinguishable from one that had no location captured at all. See the
 * "Fix and Simplify Contribution Location Architecture" audit this session
 * for the full incident.
 *
 * Two, DELIBERATELY DISTINCT, kinds of "known place" the backend can offer
 * alongside the coordinate -- never conflated, because they mean different
 * things to an admin:
 *   - confirmedPlace: this contribution answers a place-specific question,
 *     so its place is CONFIRMED, not approximated (no distance -- there is
 *     nothing approximate about it).
 *   - nearestPlace: no confirmed place exists, but a known Location happens
 *     to fall within the backend's proximity radius of the coordinate --
 *     an honest, distance-labeled approximation, never presented as if the
 *     guide confirmed it.
 */
export default function LocationPanel({
  latitude,
  longitude,
  locationLabel,
  confirmedPlace,
  nearestPlace,
}: {
  latitude: number | null;
  longitude: number | null;
  locationLabel?: string | null;
  confirmedPlace?: { name: string; locationId: string | null } | null;
  /** Omit entirely on a page that never resolves this (e.g. a list row);
   * pass the resolved value (possibly still null, meaning "nothing nearby")
   * on a detail page that does. */
  nearestPlace?: { name: string; locationId: string | null; distanceMeters: number } | null;
}) {
  const hasCoordinates = latitude != null && longitude != null;

  return (
    <div>
      <h2 className="mb-1 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-ink-faint">
        <MapPin className="h-3.5 w-3.5" /> Location
      </h2>

      {hasCoordinates ? (
        <div>
          {locationLabel ? <div className="font-bold text-ink">{locationLabel}</div> : null}
          <div className={locationLabel ? 'text-sm text-ink-soft' : 'font-bold text-ink'}>
            {latitude.toFixed(5)}, {longitude.toFixed(5)}
          </div>
          {confirmedPlace ? (
            <div className="mt-1 text-xs text-ink-faint">
              Confirmed place:{' '}
              {confirmedPlace.locationId ? (
                <Link to={`/places/${confirmedPlace.locationId}`} className="font-bold text-marigold-deep hover:underline">
                  {confirmedPlace.name}
                </Link>
              ) : (
                <span className="font-bold">{confirmedPlace.name}</span>
              )}
            </div>
          ) : nearestPlace ? (
            <div className="mt-1 text-xs italic text-ink-faint">
              Nearby known place:{' '}
              {nearestPlace.locationId ? (
                <Link to={`/places/${nearestPlace.locationId}`} className="text-marigold-deep hover:underline">
                  {nearestPlace.name}
                </Link>
              ) : (
                nearestPlace.name
              )}{' '}
              (~{Math.round(nearestPlace.distanceMeters)}m away)
            </div>
          ) : null}
        </div>
      ) : (
        <span className="text-sm italic text-ink-faint">No location captured for this contribution</span>
      )}
    </div>
  );
}
