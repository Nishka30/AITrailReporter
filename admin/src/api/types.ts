/** Mirrors backend/app/schemas/admin.py and observation_moderation.py exactly
 * -- field-for-field, so a backend change to those files is the signal to
 * update these types, not the other way around. */

export type ModerationStatus = 'pending_review' | 'approved' | 'rejected';

export type RejectionReason =
  | 'inaccurate'
  | 'unsafe'
  | 'duplicate'
  | 'poor_quality'
  | 'not_useful'
  | 'other';

export type ObservationModeration = {
  id: string;
  observation_id: string;
  status: ModerationStatus;
  decided_by: string | null;
  decided_at: string | null;
  rejection_reason: RejectionReason | null;
  rejection_note: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminOverview = {
  total_guides: number;
  total_submissions: number;
  total_observations: number;
  pending_review_count: number;
  approved_count: number;
  rejected_count: number;
  safety_critical_pending_count: number;
  active_knowledge_type_count: number;
  questions_generated_count: number;
  questions_pending_assignment_count: number;
};

export type ReviewQueueItem = {
  observation_id: string;
  knowledge_type: string;
  display_name: string;
  safety_critical: boolean;
  value: Record<string, unknown>;
  confidence: number | null;
  evidence: string | null;
  latitude: number | null;
  longitude: number | null;
  observed_at: string;
  created_at: string;
  submission_id: string;
  submission_type: string;
  guide_id: string;
  guide_name: string;
  moderation: ObservationModeration;
  nearest_known_place_name?: string | null;
  nearest_known_place_distance_meters?: number | null;
  knowledge_type_is_new: boolean;
};

export type ReviewQueueResult = {
  items: ReviewQueueItem[];
  total: number;
  page: number;
  page_size: number;
};

export type RelatedObservation = {
  observation_id: string;
  value: Record<string, unknown>;
  confidence: number | null;
  evidence: string | null;
  observed_at: string;
  guide_name: string;
  distance_meters: number | null;
  moderation_status: ModerationStatus;
};

export type SiblingObservation = {
  observation_id: string;
  knowledge_type: string;
  display_name: string;
  moderation_status: ModerationStatus;
};

export type SubmissionMediaMeta = {
  content_type: string;
  original_filename: string;
  size_bytes: number;
  duration_seconds?: number | null;
};

export type TranscriptionRead = {
  id: string;
  submission_id: string;
  status: string;
  transcript: string | null;
  language_code: string | null;
  language_probability: number | null;
  provider: string;
  model: string | null;
  mode: string | null;
  provider_request_id: string | null;
  error_message: string | null;
  attempt_count: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ReviewSourceSubmission = {
  submission_id: string;
  submission_type: string;
  raw_text: string | null;
  submitted_at: string;
  audio: SubmissionMediaMeta | null;
  photo: SubmissionMediaMeta | null;
  transcript: TranscriptionRead | null;
};

export type KnowledgeTypeState = {
  knowledge_type_id: string;
  knowledge_type: string;
  display_name: string;
  state: 'fresh' | 'aging' | 'stale' | 'missing';
  latest_observation_id: string | null;
  observed_at: string | null;
  age_hours: number | null;
  distance_meters: number | null;
  freshness_window_hours: number;
  freshness_expires_at: string | null;
  aging_threshold_hours: number | null;
  aging_expires_at: string | null;
  geographic_relevance_radius_meters: number;
  safety_critical: boolean;
  default_priority: number;
  severity_hours: number;
};

export type KnowledgeStateResult = {
  latitude: number;
  longitude: number;
  evaluation_time: string;
  knowledge_types: KnowledgeTypeState[];
  summary: {
    total_active_types: number;
    fresh_count: number;
    aging_count: number;
    stale_count: number;
    missing_count: number;
    gap_count: number;
  };
  gaps: KnowledgeTypeState[];
};

export type ReviewDetail = {
  observation: ReviewQueueItem;
  source: ReviewSourceSubmission;
  knowledge_context: KnowledgeStateResult | null;
  related_observations: RelatedObservation[];
  sibling_observations: SiblingObservation[];
};

export type PlaceSummary = {
  location_id: string;
  name: string;
  latitude: number;
  longitude: number;
  nearby_observation_count: number;
  pending_review_count: number;
  approved_count: number;
};

export type PlaceDetail = {
  location_id: string;
  name: string;
  description: string | null;
  latitude: number;
  longitude: number;
  recent_observations: ReviewQueueItem[];
};

export type ContributorSummary = {
  guide_id: string;
  name: string;
  is_active: boolean;
  submission_count: number;
  observation_count: number;
  approved_count: number;
  rejected_count: number;
  pending_review_count: number;
  last_active_at: string | null;
};

export type ContributorDetail = ContributorSummary & {
  phone_number: string | null;
  recent_observations: ReviewQueueItem[];
};

export type AdminQuestionSummary = {
  question_id: string;
  knowledge_type: string;
  display_name: string;
  gap_state: string;
  status: string;
  safety_critical: boolean;
  target_latitude: number;
  target_longitude: number;
  nearest_known_place_name: string | null;
  question_text: string | null;
  assignment_status: string | null;
  assigned_guide_name: string | null;
  created_at: string;
};

export type ReviewQueueFilters = {
  status?: string;
  knowledge_type?: string;
  safety_critical?: boolean;
  guide_id?: string;
  place_id?: string;
  source_type?: string;
  q?: string;
  sort?: string;
  page?: number;
  page_size?: number;
};
