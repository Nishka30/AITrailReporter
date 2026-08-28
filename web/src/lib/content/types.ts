/**
 * Mirrors backend/app/schemas/public.py exactly. Keep these two files in
 * sync by hand -- there is no shared codegen between the FastAPI backend
 * and this Next.js app (see plan doc).
 */

export type KnowledgeState = "fresh" | "aging" | "stale" | "missing";

export interface PublicKnowledgeType {
  knowledge_type: string;
  display_name: string;
  safety_critical: boolean;
}

export interface PublicConditionState {
  knowledge_type: string;
  display_name: string;
  safety_critical: boolean;
  state: KnowledgeState;
  observed_at: string | null;
  age_hours: number | null;
  severity_hours: number;
  latest_observation_id: string | null;
}

export interface PublicObservation {
  observation_id: string;
  knowledge_type: string;
  display_name: string;
  safety_critical: boolean;
  value: Record<string, unknown>;
  evidence: string | null;
  observed_at: string;
  submission_type: string;
  guide_name: string;
  has_photo: boolean;
  has_audio: boolean;
  photo_url: string | null;
  audio_url: string | null;
  transcript: string | null;
  nearest_place_id: string | null;
  nearest_place_name: string | null;
}

export interface PublicObservationList {
  items: PublicObservation[];
  total: number;
}

export interface PublicLocationSummary {
  location_id: string;
  name: string;
  description: string | null;
  latitude: number;
  longitude: number;
  approved_observation_count: number;
  last_activity_at: string | null;
}

export interface PublicLocationDetail extends PublicLocationSummary {
  conditions: PublicConditionState[];
  recent_observations: PublicObservation[];
  photo_count: number;
  voice_story_count: number;
}

export interface PublicSearchResult {
  query: string;
  locations: PublicLocationSummary[];
  observations: PublicObservation[];
}

export interface ListObservationsParams {
  locationId?: string;
  knowledgeType?: string;
  hasPhoto?: boolean;
  hasAudio?: boolean;
  limit?: number;
  offset?: number;
}

/** The one interface both the real API adapter and the mock adapter implement. */
export interface ContentSource {
  listLocations(limit?: number): Promise<PublicLocationSummary[]>;
  getLocation(locationId: string): Promise<PublicLocationDetail | null>;
  listObservations(params?: ListObservationsParams): Promise<PublicObservationList>;
  getObservation(observationId: string): Promise<PublicObservation | null>;
  listKnowledgeTypes(): Promise<PublicKnowledgeType[]>;
  search(query: string): Promise<PublicSearchResult>;
}
