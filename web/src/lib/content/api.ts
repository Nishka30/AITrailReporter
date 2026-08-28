/**
 * Real content source: calls the FastAPI backend's public API
 * (backend/app/api/routes/public.py). Every call is server-side `fetch`
 * with a short ISR-style revalidate window -- freshness/approval filtering
 * is entirely computed by the backend; this file never re-derives it.
 */
import type {
  ContentSource,
  ListObservationsParams,
  PublicKnowledgeType,
  PublicLocationDetail,
  PublicLocationSummary,
  PublicObservation,
  PublicObservationList,
  PublicSearchResult,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const REVALIDATE_SECONDS = 60;

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    next: { revalidate: REVALIDATE_SECONDS },
  });
  if (!res.ok) {
    throw new Error(`Request to ${path} failed with ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function getJsonOrNull<T>(path: string): Promise<T | null> {
  const res = await fetch(`${BASE_URL}${path}`, {
    next: { revalidate: REVALIDATE_SECONDS },
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`Request to ${path} failed with ${res.status}`);
  }
  return res.json() as Promise<T>;
}

/** The backend returns media URLs as root-relative paths
 * (/api/v1/public/media/...) since it doesn't know its own public origin.
 * Resolved to absolute URLs here, once, so every component downstream can
 * treat photo_url/audio_url as directly fetchable -- mirrors how mock.ts's
 * URLs are already absolute. */
function absolutize(observation: PublicObservation): PublicObservation {
  return {
    ...observation,
    photo_url: observation.photo_url ? `${BASE_URL}${observation.photo_url}` : null,
    audio_url: observation.audio_url ? `${BASE_URL}${observation.audio_url}` : null,
  };
}

export const apiContentSource: ContentSource = {
  async listLocations(limit = 50) {
    return getJson<PublicLocationSummary[]>(`/api/v1/public/locations?limit=${limit}`);
  },

  async getLocation(locationId: string) {
    const detail = await getJsonOrNull<PublicLocationDetail>(`/api/v1/public/locations/${locationId}`);
    if (!detail) return null;
    return { ...detail, recent_observations: detail.recent_observations.map(absolutize) };
  },

  async listObservations(params: ListObservationsParams = {}) {
    const query = new URLSearchParams();
    if (params.locationId) query.set("location_id", params.locationId);
    if (params.knowledgeType) query.set("knowledge_type", params.knowledgeType);
    if (params.hasPhoto) query.set("has_photo", "true");
    if (params.hasAudio) query.set("has_audio", "true");
    query.set("limit", String(params.limit ?? 25));
    query.set("offset", String(params.offset ?? 0));
    const result = await getJson<PublicObservationList>(`/api/v1/public/observations?${query.toString()}`);
    return { ...result, items: result.items.map(absolutize) };
  },

  async getObservation(observationId: string) {
    const observation = await getJsonOrNull<PublicObservation>(`/api/v1/public/observations/${observationId}`);
    return observation ? absolutize(observation) : null;
  },

  async listKnowledgeTypes() {
    return getJson<PublicKnowledgeType[]>("/api/v1/public/knowledge-types");
  },

  async search(query: string) {
    const result = await getJson<PublicSearchResult>(`/api/v1/public/search?q=${encodeURIComponent(query)}`);
    return { ...result, observations: result.observations.map(absolutize) };
  },
};
