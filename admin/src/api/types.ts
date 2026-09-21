/** Mirrors backend/app/schemas/admin.py and observation_moderation.py exactly
 * -- field-for-field, so a backend change to those files is the signal to
 * update these types, not the other way around. */

export type ModerationStatus = 'pending_review' | 'approved' | 'rejected';

export type RejectionReason =
  | 'inaccurate'
  | 'not_enough_details'
  | 'unsafe'
  | 'duplicate'
  | 'poor_quality'
  | 'not_useful'
  | 'spam'
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
  contribution_pending_review_count: number;
  contribution_approved_count: number;
  contribution_rejected_count: number;
};

export type ReviewQueueItem = {
  observation_id: string;
  knowledge_type: string;
  display_name: string;
  safety_critical: boolean;
  value: Record<string, unknown>;
  confidence: number | null;
  evidence: string | null;
  /** The observation's OWN authoritative coordinate -- ALWAYS the source of
   * truth for "where is this," never replaced or hidden by
   * nearest_known_place_name below. Both null only means this observation
   * genuinely has no coordinate. */
  latitude: number | null;
  longitude: number | null;
  /** The contribution's own human-readable location, when available.
   * Prefer this over nearest_known_place_name when both are present. */
  location_label?: string | null;
  external_place_id?: string | null;
  observed_at: string;
  created_at: string;
  submission_id: string;
  submission_type: string;
  guide_id: string;
  guide_name: string;
  moderation: ObservationModeration;
  /** OPTIONAL ENRICHMENT ONLY -- a known Location happening to be nearby.
   * Null does NOT mean "no location": check latitude/longitude for that.
   * Only ever populated on a single-item detail read, never on this list. */
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

/** One entry in a Location's multi-category classification (see
 * backend/app/services/places/category_catalog.py) -- several of these can
 * apply to the same place at once, each with its own strength/confidence. */
export type PlaceCategoryDetail = {
  kind: 'theme' | 'place_type';
  slug: string;
  display_name: string;
  relevance: number;
  confidence: number;
  is_primary: boolean;
  source: string;
};

export type PlaceSummary = {
  location_id: string;
  name: string;
  latitude: number;
  longitude: number;
  category: string | null;
  subcategory: string | null;
  source: string;
  nearby_observation_count: number;
  pending_review_count: number;
  approved_count: number;
  categories: PlaceCategoryDetail[];
};

export type PlaceQueueResult = {
  items: PlaceSummary[];
  total: number;
  page: number;
  page_size: number;
};

export type PlaceQueueFilters = {
  q?: string;
  /** Comma-separated place_type slugs, OR'd together. */
  category?: string;
  /** Comma-separated PlaceCategoryGroup keys, OR'd together (and with `category`). */
  group?: string;
  page?: number;
  page_size?: number;
};

/** One filterable place_type option with how many distinct Locations
 * currently carry it -- see backend's PlaceCategoryOption. */
export type PlaceCategoryOption = {
  kind: 'place_type';
  slug: string;
  display_name: string;
  group: string;
  count: number;
  priority: number;
};

/** A user-friendly filter section (e.g. "Food & Drink"), grouping several
 * place_types by their shared theme -- see
 * backend/app/services/places/category_ui_groups.py. */
export type PlaceCategoryGroupOptions = {
  key: string;
  label: string;
  count: number;
  options: PlaceCategoryOption[];
};

export type PlaceDetail = {
  location_id: string;
  name: string;
  description: string | null;
  latitude: number;
  longitude: number;
  category: string | null;
  subcategory: string | null;
  source: string;
  provider: string | null;
  external_place_id: string | null;
  formatted_address: string | null;
  categories: PlaceCategoryDetail[];
  created_at: string;
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

export type ContributorQueueResult = {
  items: ContributorSummary[];
  total: number;
  page: number;
  page_size: number;
};

export type ContributorQueueFilters = {
  page?: number;
  page_size?: number;
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

export type AdminQuestionQueueResult = {
  items: AdminQuestionSummary[];
  total: number;
  page: number;
  page_size: number;
};

export type AdminQuestionQueueFilters = {
  status?: string;
  assignment_status?: string;
  safety_critical?: boolean;
  page?: number;
  page_size?: number;
};

/** Admin-approval gate on rewards (Step 19) -- deliberately a SEPARATE
 * lifecycle from ObservationModeration above: this reviews whether a
 * CONTRIBUTION (submission/answer) gets paid, not whether an extracted
 * knowledge fact is fit for public visibility. One Submission can yield
 * zero-to-many Observations, so the two reviews cannot be the same table.
 * Same status/reason vocabulary as ObservationModeration on purpose (shared
 * DecisionDialog component), but a genuinely different decision. */
export type SubmissionReview = {
  id: string;
  submission_id: string;
  guide_id: string;
  status: ModerationStatus;
  decided_by: string | null;
  decided_at: string | null;
  rejection_reason: RejectionReason | null;
  rejection_note: string | null;
  reward_rule_key: string;
  /** Set only once status === 'approved'. Null while pending or rejected --
   * 0 would be ambiguous with "the rule is worth zero points". */
  reward_points_awarded: number | null;
  created_at: string;
  updated_at: string;
};

export type RewardBreakdownLine = {
  label: string;
  points: number;
};

export type ContributionQueueItem = {
  submission_id: string;
  submission_type: string;
  guide_id: string;
  guide_name: string;
  raw_text: string | null;
  submitted_at: string;
  /** The contribution's OWN authoritative coordinate -- ALWAYS the source of
   * truth for "does this contribution have a location," never replaced or
   * hidden by location_id/location_name below. Both null only means this
   * contribution genuinely has no coordinate. */
  latitude: number | null;
  longitude: number | null;
  /** The contribution's own human-readable location, straight off its
   * Submission (the guide picked a place, searched one, or an explicit
   * capture's naming lookup succeeded). Prefer this over location_name
   * when both are present -- it describes THIS coordinate directly. */
  location_label?: string | null;
  external_place_id?: string | null;
  /** OPTIONAL ENRICHMENT ONLY. Exact (location_distance_meters is null) for
   * a place-question answer's own confirmed place; otherwise, on a
   * single-item detail read only, the nearest KNOWN Location within the
   * backend's configured radius of the contribution's own coordinate --
   * an approximation, never a claim the guide confirmed it. Both null
   * simply means no known place happens to be nearby -- it must NEVER be
   * read as "no location": check latitude/longitude for that instead. */
  location_id: string | null;
  location_name: string | null;
  location_distance_meters: number | null;
  question_text: string | null;
  has_audio: boolean;
  has_photo: boolean;
  review: SubmissionReview;
  /** What this is worth right now if approved -- base rule plus any
   * eligible media bonus, resolved live from the SAME reward_rules table
   * reward_service.award() reads, so this always matches what approve()
   * would actually pay. May differ from whatever it was worth at
   * submission time if a rule's points changed since. */
  current_rule_points: number;
  reward_breakdown: RewardBreakdownLine[];
};

export type ContributionQueueResult = {
  items: ContributionQueueItem[];
  total: number;
  page: number;
  page_size: number;
};

export type ContributionDetail = {
  item: ContributionQueueItem;
  audio: SubmissionMediaMeta | null;
  photo: SubmissionMediaMeta | null;
  transcript: TranscriptionRead | null;
  guide_phone_number: string | null;
};

export type ContributionQueueFilters = {
  status?: string;
  guide_id?: string;
  submission_type?: string;
  q?: string;
  page?: number;
  page_size?: number;
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

/** Mirrors backend/app/schemas/admin_rewards.py exactly. The single source
 * of truth for reward point values -- the SAME row reward_service.award()
 * resolves at approval time and GET /api/v1/rewards/config serves to
 * mobile. Editing one here takes effect for both immediately. */
export type RewardRule = {
  id: string;
  rule_key: string;
  points: number;
  description: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type RewardRuleChange = {
  id: string;
  rule_id: string;
  rule_key: string;
  previous_points: number | null;
  new_points: number;
  changed_by: string;
  changed_at: string;
};

export type RewardRuleFilters = {
  q?: string;
};

export type RewardRuleCreatePayload = {
  rule_key: string;
  points: number;
  description: string | null;
  active: boolean;
};

export type RewardRuleUpdatePayload = {
  points?: number;
  description?: string | null;
  active?: boolean;
};
