import { apiRequest } from './client';

/**
 * The places a guide standing at some coordinate could choose to contribute
 * to (GET /api/v1/locations/candidates).
 *
 * WHY THIS EXISTS ALONGSIDE getGuideContext's `nearestKnownPlace`:
 * that one answers "where is this guide?" and resolves to exactly one place.
 * A contribution is about a SUBJECT, and the nearest listed POI is frequently
 * not it -- standing outside a hotel does not make the hotel the topic when
 * the shop next door is what you want to report on. So the position produces
 * a shortlist and the guide picks. See
 * backend/app/services/place_candidates.py for the ranking rules.
 *
 * Every candidate is a real, shared backend Location: `id` is the same
 * Location id every other endpoint uses, so two guides picking the same place
 * contribute to the same record.
 */

export interface PlaceCandidate {
  /** Backend Location id -- shared across all guides, never device-local. */
  id: string;
  name: string;
  /** Metres from the coordinate that was searched. Always 0 for an area,
   * which the guide is INSIDE rather than a distance from. */
  distanceMeters: number;
  latitude: number;
  longitude: number;
  /** TrailMind's taxonomy, not Google's raw type. Null when unclassified. */
  category: string | null;
  subcategory: string | null;
  placeKind: string | null;
  externalPlaceId: string | null;
  provider: string | null;
  formattedAddress: string | null;
  /** A neighbourhood/village the coordinate falls inside, rather than a
   * specific POI. Always offered last -- the broadest honest option. */
  isArea: boolean;
}

export interface PlaceCandidateResult {
  latitude: number;
  longitude: number;
  radiusMeters: number;
  candidates: PlaceCandidate[];
}

interface PlaceCandidateWire {
  id: string;
  name: string;
  distance_meters: number;
  latitude: number;
  longitude: number;
  category: string | null;
  subcategory: string | null;
  place_kind: string | null;
  external_place_id: string | null;
  provider: string | null;
  formatted_address: string | null;
  is_area: boolean;
}

interface PlaceCandidateResponseWire {
  latitude: number;
  longitude: number;
  radius_meters: number;
  candidates: PlaceCandidateWire[];
}

function fromWire(wire: PlaceCandidateWire): PlaceCandidate {
  return {
    id: wire.id,
    name: wire.name,
    distanceMeters: wire.distance_meters,
    latitude: wire.latitude,
    longitude: wire.longitude,
    category: wire.category,
    subcategory: wire.subcategory,
    placeKind: wire.place_kind,
    externalPlaceId: wire.external_place_id,
    provider: wire.provider,
    formattedAddress: wire.formatted_address,
    isArea: wire.is_area,
  };
}

/**
 * Never 404s and never throws on "nothing here": an empty `candidates` array
 * is the honest answer somewhere genuinely unmapped, or while Google is
 * unreachable. Only a real transport/server failure throws, so an outage is
 * never disguised as an empty place list.
 *
 * `limit` is clamped server-side, so passing something absurd is safe.
 */
export async function listPlaceCandidates(
  latitude: number,
  longitude: number,
  limit?: number
): Promise<PlaceCandidateResult> {
  const params = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
  });
  if (limit != null) params.set('limit', String(limit));

  const wire = await apiRequest<PlaceCandidateResponseWire>(
    `/api/v1/locations/candidates?${params.toString()}`
  );
  return {
    latitude: wire.latitude,
    longitude: wire.longitude,
    radiusMeters: wire.radius_meters,
    candidates: wire.candidates.map(fromWire),
  };
}

/**
 * Short, human label for a candidate's type -- "Hotel", "Shopping", "Area".
 *
 * Prefers the specific subcategory over the broad category because that is
 * what a guide recognises ("Metro Station", not "Transport"). Returns null
 * rather than inventing a label, so an unclassified place shows its distance
 * alone instead of a meaningless "Other".
 */
export function describeCandidateKind(candidate: PlaceCandidate): string | null {
  if (candidate.isArea) return candidate.subcategory ?? 'Area';
  const subcategory = candidate.subcategory;
  if (subcategory && subcategory !== 'Other') return subcategory;
  const category = candidate.category;
  if (category && category !== 'Other') return category;
  return null;
}

/** "120 m away" / "1.2 km away" / "You're inside this area". */
export function describeCandidateDistance(candidate: PlaceCandidate): string {
  if (candidate.isArea) return "You're in this area";
  const metres = candidate.distanceMeters;
  if (metres < 1000) return `${Math.round(metres)} m away`;
  return `${(metres / 1000).toFixed(1)} km away`;
}
