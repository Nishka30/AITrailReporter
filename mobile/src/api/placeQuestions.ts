import { apiRequest } from './client';

/**
 * Popular questions (Step 18) — the SECONDARY question source.
 *
 * Deliberately a much smaller shape than `Question` in api/questions.ts. A
 * popular question has no gap state, no ranking, no assignment and no
 * per-guide status, because it genuinely has none of those things: it was
 * researched from the web for a PLACE, not generated from a knowledge gap and
 * assigned to a person. Mirroring Question's shape here would imply a
 * relationship to the priority queue that does not exist.
 *
 * All web research happens on the BACKEND. This app never holds a search key,
 * never calls a search provider, and never triggers research directly — the
 * guide-scoped endpoint below refreshes it server-side when it's stale.
 */
/** How the backend is asking for this place to be reported on. Chosen per
 * place by the research step — a bridge earns a photo request, a tea stall
 * earns "is it open right now". The app uses this only to foreground the right
 * control; it never derives the reward from it. */
export type PlaceContributionKind =
  | 'photo'
  | 'voice'
  | 'observation'
  | 'experience'
  | 'status';

export interface PlaceQuestion {
  id: string;
  locationId: string;
  /** A second-person, present-tense invitation to the guide who is HERE —
   * "How does the bridge look today?", not "Is the bridge safe to cross?". */
  questionText: string;
  contributionKind: PlaceContributionKind;
  /** One short grounded line saying what research established about this place.
   * Null when nothing specific was found — never a generic filler sentence. */
  contextNote: string | null;
  displayOrder: number;
  /** Real sources the question was researched from; may be null. */
  sourceUrls: string[] | null;
  createdAt: string;
  /** What the BACKEND says THIS contribution is worth, already resolved for its
   * kind. Never computed here. */
  rewardPoints: number;
}

/** What the Questions tab shows under "Popular questions about this place".
 * `locationName` is null when the guide has no recorded location or isn't near
 * a known place — in which case `questions` is empty and the UI says so
 * plainly rather than showing questions about somewhere they aren't. */
export interface GuidePlaceQuestions {
  locationId: string | null;
  locationName: string | null;
  distanceMeters: number | null;
  questions: PlaceQuestion[];
}

interface PlaceQuestionWire {
  id: string;
  location_id: string;
  question_text: string;
  contribution_kind: PlaceContributionKind;
  context_note: string | null;
  display_order: number;
  source_urls: string[] | null;
  created_at: string;
  reward_points: number;
}

interface GuidePlaceQuestionsWire {
  location_id: string | null;
  location_name: string | null;
  distance_meters: number | null;
  questions: PlaceQuestionWire[];
}

function placeQuestionFromWire(wire: PlaceQuestionWire): PlaceQuestion {
  return {
    id: wire.id,
    locationId: wire.location_id,
    questionText: wire.question_text,
    // A backend predating this feature omits these keys entirely; defaulting
    // here keeps the declared contract honest rather than leaking `undefined`.
    contributionKind: wire.contribution_kind ?? 'observation',
    contextNote: wire.context_note ?? null,
    displayOrder: wire.display_order,
    sourceUrls: wire.source_urls,
    createdAt: wire.created_at,
    rewardPoints: wire.reward_points,
  };
}

/**
 * GET /api/v1/guides/{guideId}/popular-questions.
 *
 * Read-only from this app's perspective. The backend resolves which known
 * place the guide is at and refreshes its research if stale — that refresh is
 * best-effort server-side, so this call still returns whatever questions
 * already exist even if a research run fails.
 */
export async function listPopularQuestions(guideId: string): Promise<GuidePlaceQuestions> {
  const wire = await apiRequest<GuidePlaceQuestionsWire>(
    `/api/v1/guides/${guideId}/popular-questions`
  );
  return {
    locationId: wire.location_id,
    locationName: wire.location_name,
    distanceMeters: wire.distance_meters,
    questions: wire.questions.map(placeQuestionFromWire),
  };
}

export interface PlaceQuestionAnswerResult {
  placeQuestionId: string;
  submissionId: string;
  pointsAwarded: number;
}

interface PlaceQuestionAnswerWire {
  place_question_id: string;
  submission_id: string;
  guide_id: string;
  answer_text: string;
  answered_at: string;
  points_awarded: number;
}

/**
 * POST /api/v1/place-questions/{id}/answers — called by the sync engine, not
 * directly by a screen (answers are written locally first and synced later,
 * exactly like knowledge-gap answers).
 *
 * Idempotent on clientAnswerId: a replayed sync returns 200 with
 * points_awarded = 0 because the guide was already credited on the first
 * success. The app must NOT add that number to a running total a second time.
 */
export async function submitPlaceQuestionAnswer(
  placeQuestionId: string,
  guideId: string,
  clientAnswerId: string,
  answerText: string,
  answeredAt: string
): Promise<PlaceQuestionAnswerResult> {
  const wire = await apiRequest<PlaceQuestionAnswerWire>(
    `/api/v1/place-questions/${placeQuestionId}/answers`,
    {
      method: 'POST',
      body: {
        guide_id: guideId,
        client_answer_id: clientAnswerId,
        answer_text: answerText,
        answered_at: answeredAt,
      },
    }
  );
  return {
    placeQuestionId: wire.place_question_id,
    submissionId: wire.submission_id,
    pointsAwarded: wire.points_awarded,
  };
}
