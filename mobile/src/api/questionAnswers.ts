import { apiRequest } from './client';
import { questionFromWire, type Question } from './questions';

export interface SubmitAnswerRequest {
  questionId: string;
  guideId: string;
  /** Makes this call idempotent -- see backend QuestionAnswer.client_answer_id. */
  clientAnswerId: string;
  answerText: string;
  /** ISO-8601, timezone-aware -- when the guide actually answered, not when
   * it's sent. */
  answeredAt: string;
}

/**
 * POST /api/v1/questions/{questionId}/answers. Idempotent on clientAnswerId:
 * calling this again with the same clientAnswerId and the same payload
 * returns the same result instead of creating a duplicate answer. Possible
 * ApiError statuses (see backend/app/api/routes/questions.py):
 *   404 - question not found
 *   400 - question has no current assignment, or its assignment was cancelled
 *   403 - this question is assigned to a DIFFERENT guide
 *   409 - already answered (a different clientAnswerId), or this
 *         clientAnswerId was reused with different answer data
 * Returns the full updated Question (its `assignment.status` becomes
 * 'completed' and `answer` is populated) so the caller can refresh its view
 * from one response.
 */
export async function submitAnswer(req: SubmitAnswerRequest): Promise<Question> {
  const wire = await apiRequest<Parameters<typeof questionFromWire>[0]>(
    `/api/v1/questions/${req.questionId}/answers`,
    {
      method: 'POST',
      body: {
        guide_id: req.guideId,
        client_answer_id: req.clientAnswerId,
        answer_text: req.answerText,
        answered_at: req.answeredAt,
      },
    }
  );
  return questionFromWire(wire);
}
