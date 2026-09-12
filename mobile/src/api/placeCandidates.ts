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
 * Session-only cache in front of listPlaceCandidates, keyed on "roughly the
 * same spot, recently enough".
 *
 * WHY THIS EXISTS: the place-picker screen (PlacePickerScreen.tsx) is torn
 * down and rebuilt each time it's shown -- "Change Location" un-mounts
 * whichever tab is active and mounts the picker fresh, so nothing in the
 * component itself survives between one open and the next. A guide who picks
 * a place, then taps "Change Location" moments later without having gone
 * anywhere, was paying for the SAME Google/backend discovery round trip
 * again for what is provably the same answer. This module-level cache
 * survives across those mounts (it lives for as long as the app process
 * does, same idea as the small in-process caches on the backend's own
 * Google-provider client) and is reused only when both hold:
 *
 *   - fetched recently enough (CANDIDATE_CACHE_TTL_MS) -- this is a
 *     same-session convenience, not a substitute for the backend's own much
 *     longer discovery/refresh windows, so it expires quickly.
 *   - fetched from close enough to the current position
 *     (CANDIDATE_CACHE_REUSE_RADIUS_METERS) -- deliberately tight. This is
 *     about "the guide hasn't actually gone anywhere," not approximating a
 *     new spot with an old list; a guide who walked to a genuinely different
 *     corner of the block must get a real, current answer.
 *
 * Falls straight through to a real fetch (and refreshes the cache) whenever
 * either check fails, exactly as if this wrapper didn't exist -- so the
 * worst case is identical to today's behaviour, never worse.
 */
interface CachedPlaceCandidates {
  latitude: number;
  longitude: number;
  fetchedAt: number;
  result: PlaceCandidateResult;
}

let placeCandidatesCache: CachedPlaceCandidates | null = null;

const CANDIDATE_CACHE_TTL_MS = 5 * 60 * 1000;
const CANDIDATE_CACHE_REUSE_RADIUS_METERS = 100;

/** Great-circle distance in metres. Used only to judge whether a cached
 * result is still trustworthy -- never sent anywhere, and not a substitute
 * for the authoritative per-candidate distances the backend computes. */
function metresBetween(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const EARTH_RADIUS_METERS = 6_371_000;
  const toRadians = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRadians(lat2 - lat1);
  const dLon = toRadians(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_METERS * Math.asin(Math.min(1, Math.sqrt(a)));
}

/**
 * Same contract and return shape as listPlaceCandidates -- reuses a recent
 * result for practically the same coordinate instead of always calling the
 * backend. See the cache's own doc comment above for the reuse rule.
 *
 * `limit` is passed straight through to a real fetch when one happens; it is
 * NOT part of the cache key. In practice this screen always calls with the
 * same default limit, and reusing a slightly-more-generous cached list for a
 * smaller request is harmless -- callers only ever read the list, never rely
 * on its length matching `limit` exactly.
 */
export async function listPlaceCandidatesCached(
  latitude: number,
  longitude: number,
  limit?: number
): Promise<PlaceCandidateResult> {
  if (placeCandidatesCache) {
    const age = Date.now() - placeCandidatesCache.fetchedAt;
    const moved = metresBetween(
      latitude,
      longitude,
      placeCandidatesCache.latitude,
      placeCandidatesCache.longitude
    );
    if (age <= CANDIDATE_CACHE_TTL_MS && moved <= CANDIDATE_CACHE_REUSE_RADIUS_METERS) {
      return placeCandidatesCache.result;
    }
  }
  const result = await listPlaceCandidates(latitude, longitude, limit);
  placeCandidatesCache = { latitude, longitude, fetchedAt: Date.now(), result };
  return result;
}

/**
 * Forces the next listPlaceCandidatesCached call to hit the network
 * regardless of distance or age. Used by an explicit refresh gesture (a
 * "Refresh"/"Try again" tap, or pull-to-refresh) -- asking to refresh means
 * "don't just hand me back what you already had," so those stay exactly as
 * network-backed as they were before this cache existed.
 */
export function invalidatePlaceCandidatesCache(): void {
  placeCandidatesCache = null;
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
