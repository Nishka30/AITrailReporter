import type { PublicPlaceQuestion } from "@/lib/content";
import { formatDate, timeAgoLabel } from "@/lib/content/freshness";

/**
 * "Answers about this place" -- active PlaceQuestions with at least one
 * approved answer (the backend never returns an unanswered question; see
 * list_public_place_questions). Every answer carries its guide and its
 * absolute date, so an old answer can't read as today's.
 */
function AnswerCard({ question }: { question: PublicPlaceQuestion }) {
  return (
    <article className="flex w-full flex-col rounded-xl border border-border bg-paper-elevated p-6">
      <h3 className="font-heading text-lg font-bold leading-snug text-ink">{question.question_text}</h3>
      {question.context_note && <p className="mt-1.5 text-sm italic leading-relaxed text-ink-faint">{question.context_note}</p>}
      <div className="mt-4 space-y-4 border-t border-border pt-4">
        {question.answers.map((answer) => (
          <div key={answer.submission_id}>
            <p className="text-[15px] leading-[1.8] text-ink-soft">{answer.answer_text}</p>
            <p className="mt-1.5 text-xs text-ink-faint">
              <span className="font-semibold text-ink-soft">{answer.guide_name}</span> · {formatDate(answer.answered_at)} (
              {timeAgoLabel(answer.answered_at).toLowerCase()})
            </p>
          </div>
        ))}
      </div>
    </article>
  );
}

export function PopularQuestionsSection({ questions }: { questions: PublicPlaceQuestion[] }) {
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      {questions.map((question) => (
        <AnswerCard key={question.place_question_id} question={question} />
      ))}
    </div>
  );
}
