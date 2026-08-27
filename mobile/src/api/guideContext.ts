import { ApiError, apiRequest } from './client';

/**
 * Read-only geographic + knowledge context for a guide, used by the Explore
 * tab to build genuinely contextual discovery prompts (Step 16).
 *
 * Both endpoints already existed and are reused UNCHANGED — Explore adds no
 * new backend surface for context. Deliberately so: the whole point of Explore
 * is to make better use of knowledge the system already has, and a new
 * endpoint would have duplicated logic that
 * app/api/routes/guides.py already implements correctly.
 */

export interface NearestKnownPlace {
  id: string;
  name: string;
  distanceMeters: number;
}

export interface GuideContext {
  guideId: string;
  guideName: string;
  latitude: number;
  longitude: number;
  recordedAt: string;
  accuracyMeters: number | null;
  /** Null when no KNOWN place is within the backend's configured context
   * radius. Explore must then avoid claiming the guide is "near" anywhere —
   * see explorePrompts.ts. */
  nearestKnownPlace: NearestKnownPlace | null;
}

interface NearestKnownPlaceWire {
  id: string;
  name: string;
  distance_meters: number;
}

interface GuideContextWire {
  guide_id: string;
  guide_name: string;
  latitude: number;
  longitude: number;
  recorded_at: string;
  accuracy_meters: number | null;
  nearest_known_place: NearestKnownPlaceWire | null;
}

function placeFromWire(wire: NearestKnownPlaceWire | null): NearestKnownPlace | null {
  return wire ? { id: wire.id, name: wire.name, distanceMeters: wire.distance_meters } : null;
}

/**
 * GET /api/v1/guides/{guideId}/context.
 *
 * Returns null when the guide has no recorded location yet. The backend
 * signals that with a 404 (same as /knowledge-state and /locations/latest),
 * which is a legitimate, expected state for a guide who hasn't captured a
 * location — NOT an error worth showing. Every other failure still throws, so
 * a real outage is never disguised as "no location".
 */
export async function getGuideContext(guideId: string): Promise<GuideContext | null> {
  try {
    const wire = await apiRequest<GuideContextWire>(`/api/v1/guides/${guideId}/context`);
    return {
      guideId: wire.guide_id,
      guideName: wire.guide_name,
      latitude: wire.latitude,
      longitude: wire.longitude,
      recordedAt: wire.recorded_at,
      accuracyMeters: wire.accuracy_meters,
      nearestKnownPlace: placeFromWire(wire.nearest_known_place),
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

/** A knowledge type's live state at the guide's location. Mirrors the
 * backend's KnowledgeTypeState — only the fields Explore actually uses. */
export interface KnowledgeTypeState {
  knowledgeType: string;
  displayName: string;
  /** 'fresh' | 'aging' | 'stale' | 'missing' — the backend's live evaluation,
   * never recomputed on the device. */
  state: string;
  ageHours: number | null;
  safetyCritical: boolean;
}

interface KnowledgeStateWire {
  knowledge_state: {
    knowledge_types: {
      knowledge_type: string;
      display_name: string;
      state: string;
      age_hours: number | null;
      safety_critical: boolean;
    }[];
  };
}

/**
 * GET /api/v1/guides/{guideId}/knowledge-state.
 *
 * Explore uses this to know what the system ALREADY knows about where the
 * guide is standing, so a prompt can say something true and specific instead
 * of asking generically. Same 404-means-no-location contract as above.
 */
export async function getGuideKnowledgeState(
  guideId: string
): Promise<KnowledgeTypeState[] | null> {
  try {
    const wire = await apiRequest<KnowledgeStateWire>(
      `/api/v1/guides/${guideId}/knowledge-state`
    );
    return wire.knowledge_state.knowledge_types.map((t) => ({
      knowledgeType: t.knowledge_type,
      displayName: t.display_name,
      state: t.state,
      ageHours: t.age_hours,
      safetyCritical: t.safety_critical,
    }));
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}
