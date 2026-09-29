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
  /** Every photo attached to this observation's submission (multi-photo
   * support) -- empty, never null, when none exists. */
  photo_urls: string[];
  audio_url: string | null;
  transcript: string | null;
  nearest_place_id: string | null;
  nearest_place_name: string | null;
  /** Set only for a category-knowledge observation (the primary knowledge
   * system) -- names the Location category it verifies. Null for a
   * hazard/knowledge-type report. */
  category_slug?: string | null;
  category_display_name?: string | null;
  /** The contribution's own place label ("Lukla main street"), when the
   * guide picked or searched one -- describes this report's coordinate. */
  location_label?: string | null;
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
  /** Only when returned as a neighbour (PublicLocationDetail.nearby). */
  distance_meters?: number | null;
  /** Active categories: primary place_type first, then themes by relevance. */
  categories?: PublicCategoryLabel[];
}

export interface PublicCategoryLabel {
  slug: string;
  kind: "theme" | "place_type" | string;
  display_name: string;
}

/** Derived coverage state of one category (backend
 * category_knowledge.compute_category_state) -- never stored. */
export type CategoryState = "fresh" | "stale" | "partially_stale" | "missing";

/** One TrailMind-VERIFIED fact -- a guide's approved observation confirmed
 * it. Pending/unverified knowledge is never sent to the public site. */
export interface PublicVerifiedKnowledge {
  knowledge_id: string;
  knowledge_text: string;
  last_verified_at: string;
  fresh: boolean;
}

/** One of a Location's active categories, straight from the database
 * (relevance/active rules applied server-side), most relevant first. */
export interface PublicLocationCategory {
  slug: string;
  kind: "theme" | "place_type" | string;
  display_name: string;
  relevance: number;
  is_primary: boolean;
  state: CategoryState;
  verified_knowledge: PublicVerifiedKnowledge[];
}

/** A Location's reusable, structured, WEB-RESEARCHED summary (see backend
 * app/db/models/location_research_summary.py). Deliberately separate from
 * live TrailMind data (conditions/recent_observations) and from any future
 * TrailMind-verified knowledge -- background/reference information only,
 * never presented as current or verified. */
export interface PlaceResearchSummary {
  status: string;
  description: string | null;
  known_for: string | null;
  highlights: string[];
  things_to_do: string[];
  important_facts: string[];
  practical_info: string | null;
  warnings: string[];
  source_urls: string[];
  source_titles: string[];
  /** Age of the EVIDENCE this summary is built from -- null when nothing has
   * ever completed successfully for this Location. */
  researched_at: string | null;
}

export interface PublicPlaceQuestionAnswer {
  submission_id: string;
  answer_text: string;
  guide_name: string;
  answered_at: string;
}

/** An active PlaceQuestion with >= 1 approved answer -- a question with zero
 * approved answers is never returned by the backend, so `answers` is never
 * empty here. */
export interface PublicPlaceQuestion {
  place_question_id: string;
  question_text: string;
  context_note: string | null;
  answers: PublicPlaceQuestionAnswer[];
}

/** One stop on a Route. `status` reuses KnowledgeState so the existing
 * freshnessLabel/freshnessTone/timeAgoLabel helpers apply unchanged. */
export interface PublicRouteStop {
  route_stop_id: string;
  location_id: string;
  name: string;
  sequence_order: number;
  stop_label: string | null;
  elevation_meters: number | null;
  latitude: number;
  longitude: number;
  status: KnowledgeState;
  last_observed_at: string | null;
  age_hours: number | null;
}

export interface PublicRoute {
  route_id: string;
  slug: string;
  name: string;
  description: string | null;
  stops: PublicRouteStop[];
}

export interface PublicLocationDetail extends PublicLocationSummary {
  conditions: PublicConditionState[];
  recent_observations: PublicObservation[];
  photo_count: number;
  voice_story_count: number;
  /** Background/reference information from web research -- explicitly NOT
   * live TrailMind data. Null when this Location has never had a summary
   * attempt. */
  research_summary: PlaceResearchSummary | null;
  /** Active PlaceQuestions with at least one approved answer. Empty when
   * this Location has none (yet). */
  popular_questions: PublicPlaceQuestion[];
  /** null for the overwhelming majority of Locations -- only set when this
   * Location is a stop on a seeded Route. */
  route: PublicRoute | null;
  categories: PublicLocationCategory[];
  nearby: PublicLocationSummary[];
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
