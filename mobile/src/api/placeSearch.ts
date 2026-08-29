import { apiRequest } from './client';

/** One real, named place a guide might mean — from
 * backend/app/services/geocoding.py (OpenStreetMap Nominatim). `label` is
 * the full display string; the app never assembles its own from raw parts. */
export interface PlaceSearchResult {
  label: string;
  latitude: number;
  longitude: number;
}

interface PlaceSearchResponseWire {
  results: { label: string; latitude: number; longitude: number }[];
}

/**
 * GET /api/v1/guides/{guideId}/place-search?q=... — place-name autocomplete
 * for describing a memory/old photo without exact coordinates. Read-only,
 * stateless: selecting a result is an on-device concern (see
 * src/components/PlaceAutocomplete.tsx). Biased toward this guide's own
 * recorded location history server-side, never restricted to it.
 *
 * Throws NetworkError/ApiError like every other endpoint module — callers
 * treat "search failed" as "no suggestions right now", never as a reason to
 * block saving a memory (see the offline-first rule: place search is a
 * convenience, not a requirement).
 */
export async function searchPlaces(guideId: string, query: string): Promise<PlaceSearchResult[]> {
  const wire = await apiRequest<PlaceSearchResponseWire>(
    `/api/v1/guides/${guideId}/place-search?q=${encodeURIComponent(query)}`
  );
  return wire.results;
}
