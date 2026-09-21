/**
 * THE single "what should an admin see for this contribution's location"
 * rule, shared by every list card and detail page so it can never drift
 * between them.
 *
 * Priority, matching the three-layer model this session settled on:
 *   1. location_label   -- the CONTRIBUTION's own human-readable name (the
 *      guide picked/searched a place, or an explicit capture's naming
 *      lookup succeeded). Authoritative, shown as-is.
 *   2. a nearby/confirmed known Location -- enrichment, never the
 *      contribution's own data. A CONFIRMED place (a place-question
 *      answer's exact place) is shown plainly; an APPROXIMATE nearby match
 *      is prefixed "Near " so an admin never mistakes proximity for
 *      certainty.
 *   3. latitude/longitude present but nothing human-readable resolved --
 *      an honest "Location captured" rather than raw numbers or a claim
 *      of "not specified" (the coordinate IS there, just unnamed).
 *   4. no coordinate at all -- the only case "no location" is actually true.
 *
 * Raw coordinates are deliberately NOT part of this string -- an admin
 * reviewer doesn't need to read "40.43605, -74.46057" to do their job. They
 * remain fully available via the API/database (for maps, for the Travelers
 * website) and are attached here only as an optional tooltip value for a
 * caller that wants one, never as the primary visible text.
 */
export interface LocationDisplayInput {
  latitude: number | null;
  longitude: number | null;
  locationLabel?: string | null;
  /** A known Location's name, already resolved by the backend (either the
   * exact place a place-question answer confirms, or an approximate
   * proximity match) -- never computed client-side. */
  nearbyPlaceName?: string | null;
  /** True only for a CONFIRMED place (e.g. a place-question's own
   * location) -- never true for a distance-based proximity match. */
  nearbyIsConfirmed?: boolean;
}

export interface LocationDisplay {
  /** The one line to render, e.g. "Bicentennial Park", "Near Bicentennial
   * Park", "Location captured", or "No location captured". */
  text: string;
  /** True when a real coordinate exists, regardless of whether a
   * human-readable name was resolved -- lets a caller decide whether to
   * offer a coordinate tooltip/title at all. */
  hasCoordinates: boolean;
}

export function describeContributionLocation(input: LocationDisplayInput): LocationDisplay {
  const hasCoordinates = input.latitude != null && input.longitude != null;
  if (input.locationLabel) {
    return { text: input.locationLabel, hasCoordinates };
  }
  if (input.nearbyPlaceName) {
    return {
      text: input.nearbyIsConfirmed ? input.nearbyPlaceName : `Near ${input.nearbyPlaceName}`,
      hasCoordinates,
    };
  }
  if (hasCoordinates) {
    return { text: 'Location captured', hasCoordinates: true };
  }
  return { text: 'No location captured', hasCoordinates: false };
}

/** For an optional coordinate tooltip (e.g. `title="..."`) -- never the
 * primary UI text, see this module's docstring. */
export function coordinateTooltip(latitude: number | null, longitude: number | null): string | undefined {
  if (latitude == null || longitude == null) return undefined;
  return `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
}
