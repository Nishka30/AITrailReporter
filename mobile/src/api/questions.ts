import { apiRequest } from './client';

/** Mirrors the backend's Question.status EXACTLY (see
 * backend/app/db/models/question.py) -- a FOURTH state machine, independent
 * of SyncStatus, TranscriptionStatus, and ExtractionStatus. Answers "did LLM
 * processing turn a knowledge gap into a usable question?" */
export type QuestionStatus = 'pending' | 'processing' | 'generated' | 'failed';

/** Mirrors QuestionAssignment.status EXACTLY -- a FIFTH, separate state
 * machine again: "what is the guide doing with this question?" 'assigned'
 * and (since Step 13) 'completed' are the only statuses this app's own
 * answer flow ever produces; 'active'/'cancelled' remain reserved for a
 * future step -- see backend/app/db/models/question_assignment.py. */
export type AssignmentStatus = 'assigned' | 'active' | 'completed' | 'cancelled';

export interface QuestionAssignment {
  id: string;
  guideId: string;
  guideName: string;
  status: AssignmentStatus;
  assignedAt: string;
  answeredAt: string | null;
}

/** A guide's persisted answer to a question (Step 13). No LLM/provider
 * fields here -- answering never calls a provider, see
 * backend/app/schemas/question_answer.py. */
export interface QuestionAnswer {
  id: string;
  questionId: string;
  assignmentId: string;
  guideId: string;
  answerText: string;
  submissionId: string;
  answeredAt: string;
}

/** Mirrors the backend's KnowledgeState Literal (Step 10, extended in Step
 * 14 with 'aging') -- 'fresh' never appears on a Question (a fresh knowledge
 * type is not a gap and can't produce one). A point-in-time snapshot of the
 * gap's state when the question was generated -- never recomputed, so it
 * stays truthful even if live knowledge state later changes. */
export type GapState = 'missing' | 'aging' | 'stale';

export interface Question {
  id: string;
  knowledgeType: string;
  displayName: string;
  gapState: GapState;
  targetLatitude: number;
  targetLongitude: number;
  nearestKnownPlaceName: string | null;
  nearestKnownPlaceDistanceMeters: number | null;
  safetyCritical: boolean;
  defaultPriority: number;
  stalenessSeverityHours: number;
  gapRank: number;
  questionText: string | null;
  shortContext: string | null;
  status: QuestionStatus;
  errorMessage: string | null;
  assignment: QuestionAssignment | null;
  answer: QuestionAnswer | null;
}

interface QuestionAssignmentWire {
  id: string;
  guide_id: string;
  guide_name: string;
  status: AssignmentStatus;
  assigned_at: string;
  answered_at: string | null;
}

interface QuestionAnswerWire {
  id: string;
  question_id: string;
  assignment_id: string;
  guide_id: string;
  answer_text: string;
  submission_id: string;
  answered_at: string;
}

interface QuestionWire {
  id: string;
  knowledge_type: string;
  display_name: string;
  gap_state: GapState;
  target_latitude: number;
  target_longitude: number;
  nearest_known_place_name: string | null;
  nearest_known_place_distance_meters: number | null;
  safety_critical: boolean;
  default_priority: number;
  staleness_severity_hours: number;
  gap_rank: number;
  question_text: string | null;
  short_context: string | null;
  status: QuestionStatus;
  error_message: string | null;
  assignment: QuestionAssignmentWire | null;
  answer: QuestionAnswerWire | null;
}

/** Exported so api/questionAnswers.ts can map the same QuestionRead shape
 * returned by POST .../answers without duplicating this mapping. */
export function questionFromWire(wire: QuestionWire): Question {
  return {
    id: wire.id,
    knowledgeType: wire.knowledge_type,
    displayName: wire.display_name,
    gapState: wire.gap_state,
    targetLatitude: wire.target_latitude,
    targetLongitude: wire.target_longitude,
    nearestKnownPlaceName: wire.nearest_known_place_name,
    nearestKnownPlaceDistanceMeters: wire.nearest_known_place_distance_meters,
    safetyCritical: wire.safety_critical,
    defaultPriority: wire.default_priority,
    stalenessSeverityHours: wire.staleness_severity_hours,
    gapRank: wire.gap_rank,
    questionText: wire.question_text,
    shortContext: wire.short_context,
    status: wire.status,
    errorMessage: wire.error_message,
    assignment: wire.assignment
      ? {
          id: wire.assignment.id,
          guideId: wire.assignment.guide_id,
          guideName: wire.assignment.guide_name,
          status: wire.assignment.status,
          assignedAt: wire.assignment.assigned_at,
          answeredAt: wire.assignment.answered_at,
        }
      : null,
    answer: wire.answer
      ? {
          id: wire.answer.id,
          questionId: wire.answer.question_id,
          assignmentId: wire.answer.assignment_id,
          guideId: wire.answer.guide_id,
          answerText: wire.answer.answer_text,
          submissionId: wire.answer.submission_id,
          answeredAt: wire.answer.answered_at,
        }
      : null,
  };
}

/**
 * GET /api/v1/guides/{guideId}/questions. Read-only -- never triggers
 * generation. This app never generates questions itself (that's a
 * server/backend-triggered action); it only displays whatever has already
 * been assigned. Manual refresh only -- no polling.
 */
export async function listAssignedQuestions(guideId: string): Promise<Question[]> {
  const wire = await apiRequest<QuestionWire[]>(`/api/v1/guides/${guideId}/questions`);
  return wire.map(questionFromWire);
}
