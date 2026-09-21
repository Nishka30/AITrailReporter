import { MapPin } from 'lucide-react';
import { Link } from 'react-router-dom';

import { coordinateTooltip, describeContributionLocation } from '../../lib/locationDisplay';

/**
 * THE single "where is this contribution" display, shared by every
 * contribution-facing detail page (Contribution Review, Content Review) --
 * see src/lib/locationDisplay.ts for the shared priority rule this renders
 * (also used by the list cards, so wording never drifts between the queue
 * and its detail page).
 *
 * Deliberately does NOT show raw latitude/longitude as the primary text --
 * an admin reviewer doesn't need to read "40.43605, -74.46057" to do their
 * job. The exact coordinate stays fully available in the API/database (for
 * a future map view, and for the Travelers website); here it is attached
 * only as a hover tooltip on the location line, never printed outright.
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
 *     guide confirmed it. Shown as "Near <place>", not "<place>".
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
  const place = confirmedPlace ?? nearestPlace ?? null;
  const location = describeContributionLocation({
    latitude,
    longitude,
    locationLabel,
    nearbyPlaceName: place?.name ?? null,
    nearbyIsConfirmed: confirmedPlace != null,
  });

  return (
    <div>
      <h2 className="mb-1 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-ink-faint">
        <MapPin className="h-3.5 w-3.5" /> Location
      </h2>

      <div
        className={location.hasCoordinates ? 'font-bold text-ink' : 'text-sm italic text-ink-faint'}
        title={coordinateTooltip(latitude, longitude)}
      >
        {place?.locationId ? (
          <Link to={`/places/${place.locationId}`} className="text-marigold-deep hover:underline">
            {location.text}
          </Link>
        ) : (
          location.text
        )}
      </div>
      {nearestPlace && !confirmedPlace ? (
        <div className="mt-0.5 text-xs italic text-ink-faint">
          (~{Math.round(nearestPlace.distanceMeters)}m away)
        </div>
      ) : null}
    </div>
  );
}
