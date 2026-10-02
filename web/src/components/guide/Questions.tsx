import type { PublicOpenQuestion, PublicPlaceQuestion } from "@/lib/content";
import { formatDate } from "@/lib/content/freshness";
import { Avatar, AvatarStack, StatusChip, type ChipTone } from "./primitives";
import { Icon } from "./Icons";

function answerAge(iso: string, nowMs: number): { tone: ChipTone; label: string } {
  const days = (nowMs - new Date(iso).getTime()) / 86_400_000;
  if (days <= 7) return { tone: "fresh", label: "Recently checked" };
  if (days <= 30) return { tone: "due", label: "Due for a check" };
  return { tone: "old", label: "Not recently checked" };
}

function AnsweredCard({ question, nowMs, askHref }: { question: PublicPlaceQuestion; nowMs: number; askHref: string }) {
  const answer = question.answers[0];
  const age = answerAge(answer.answered_at, nowMs);
  return (
    <article className="flex h-full flex-col rounded-[8px] border border-border bg-white p-6 sm:p-[25px]">
      <div>
        <StatusChip tone={age.tone}>{age.label}</StatusChip>
      </div>
      <h3 className="mt-4 text-[19px] font-bold leading-[1.45] tracking-[-0.015em] text-ink">{question.question_text}</h3>
      <p className="mt-2.5 text-[16px] leading-[1.8] text-ink-soft">{answer.answer_text}</p>
      <div className="mt-auto pt-6">
        <div className="flex items-center gap-3">
          <Avatar name={answer.guide_name} />
          <div className="leading-tight">
            <p className="text-[14px] font-bold text-[#344c5b]">
              {answer.guide_name} · 1 guide · {question.answers.length} {question.answers.length === 1 ? "answer" : "answers"}
            </p>
            <p className="mt-1 text-[14px] text-ink-meta">{formatDate(answer.answered_at)}</p>
          </div>
        </div>
        <div className="mt-5 flex justify-end border-t border-border-soft pt-4">
          <a href={askHref} className="text-[14px] text-ink-soft hover:text-ink hover:underline">
            Request a fresh check
          </a>
        </div>
      </div>
    </article>
  );
}

function OpenCard({ question, askHref }: { question: PublicOpenQuestion; askHref: string }) {
  return (
    <article className="flex h-full flex-col rounded-[8px] border border-border bg-[#fbfcfc] p-6 sm:p-[25px]">
      <div>
        <StatusChip tone="open" icon="help">
          Awaiting a local check
        </StatusChip>
      </div>
      <h3 className="mt-4 text-[19px] font-bold leading-[1.45] tracking-[-0.015em] text-ink">{question.question_text}</h3>
      <p className="mt-2.5 text-[16px] leading-[1.8] text-ink-soft">
        {question.context_note ??
          "No local guide has answered this yet. When one does, the answer appears here with their name and the date they checked."}
      </p>
      <div className="mt-auto pt-6">
        <div className="flex items-center justify-between border-t border-border-soft pt-4">
          <span className="text-[13px] text-ink-faint">A question travellers ask here</span>
          <a href={askHref} className="group inline-flex items-center gap-1.5 text-[14px] font-bold text-accent-deep">
            <span className="group-hover:underline">Ask a guide</span>
            <Icon name="chat" size={15} strokeWidth={1.9} />
          </a>
        </div>
      </div>
    </article>
  );
}

export function AskBlock({ placeName, guideNames, askHref }: { placeName: string; guideNames: string[]; askHref: string }) {
  return (
    <div className="flex h-full flex-col justify-center rounded-[8px] bg-deep p-7 text-white sm:p-8">
      {guideNames.length > 0 && <AvatarStack names={guideNames.slice(0, 4)} />}
      <p className="mt-6 text-[11.5px] font-bold uppercase tracking-[0.14em] text-[#9fd3e2]">Something more specific?</p>
      <h3 className="mt-3 text-[27px] font-bold leading-[1.25] tracking-[-0.025em]">
        Your dates.
        <br />
        Your question.
      </h3>
      <p className="mt-4 text-[16px] leading-[1.75] text-white/85">
        Tell us what you need to know about {placeName}. A question can become the next thing a guide checks.
      </p>
      <div className="mt-6">
        <a
          href={askHref}
          className="inline-flex min-h-[44px] items-center gap-2.5 rounded-[5px] bg-white px-[18px] text-[15px] font-bold text-ink hover:bg-paper-muted"
        >
          Ask a local guide
          <Icon name="chat" size={17} strokeWidth={1.9} />
        </a>
        <p className="mt-3 text-[13px] text-white/70">No booking needed to ask.</p>
      </div>
    </div>
  );
}

const CARD_SLOTS = 5;

/**
 * "Current answers, with local context": guide-answered questions first
 * (with who and when), then curated questions still awaiting a local check,
 * with the dark "your question" block in the grid -- then every remaining
 * question as a compact list.
 */
export function QuestionsSection({
  placeName,
  answered,
  open,
  guideNames,
  askHref,
  nowMs,
}: {
  placeName: string;
  answered: PublicPlaceQuestion[];
  open: PublicOpenQuestion[];
  guideNames: string[];
  askHref: string;
  nowMs: number;
}) {
  const cards = [
    ...answered.map((q) => ({ id: q.place_question_id, node: <AnsweredCard question={q} nowMs={nowMs} askHref={askHref} /> })),
    ...open.map((q) => ({ id: q.place_question_id, node: <OpenCard question={q} askHref={askHref} /> })),
  ];
  const featured = cards.slice(0, CARD_SLOTS);
  const rest = open.slice(Math.max(0, CARD_SLOTS - answered.length));

  return (
    <div>
      <div className="grid gap-5 md:grid-cols-2">
        {featured.map((c) => (
          <div key={c.id}>{c.node}</div>
        ))}
        <AskBlock placeName={placeName} guideNames={guideNames} askHref={askHref} />
      </div>

      {rest.length > 0 && (
        <details className="group mt-8 rounded-[8px] border border-border bg-white">
          <summary className="flex cursor-pointer items-center justify-between gap-4 px-6 py-5">
            <span className="text-[16px] font-bold text-ink">
              {rest.length} more question{rest.length === 1 ? "" : "s"} travellers ask about {placeName}
            </span>
            <Icon name="chevronDown" size={18} className="text-ink-meta transition-transform group-open:rotate-180" />
          </summary>
          <ul className="divide-y divide-border-soft border-t border-border-soft">
            {rest.map((q) => (
              <li key={q.place_question_id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-4">
                <span className="text-[15.5px] text-ink">{q.question_text}</span>
                <StatusChip tone="open" icon="help">
                  Awaiting a local check
                </StatusChip>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
