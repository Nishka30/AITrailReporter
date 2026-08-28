"use client";

import { useEffect, useRef, useState, useTransition, type FormEvent, type KeyboardEvent } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import type { PublicLocationSummary } from "@/lib/content";
import { askAnything, type GlobalAskResult } from "@/lib/content/globalAsk";
import { freshnessLabel, freshnessTone, timeAgoLabel } from "@/lib/content/freshness";

const TONE_TEXT: Record<string, string> = {
  good: "text-ok",
  warn: "text-marigold-deep",
  bad: "text-fix",
  neutral: "text-ink-faint",
};
const TONE_DOT: Record<string, string> = {
  good: "bg-ok",
  warn: "bg-marigold-deep",
  bad: "bg-fix",
  neutral: "bg-ink-faint",
};

export function AskAnything({ locations }: { locations: PublicLocationSummary[] }) {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [result, setResult] = useState<GlobalAskResult | null>(null);
  const [pending, startTransition] = useTransition();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [question]);

  function run(q: string) {
    const trimmed = q.trim();
    if (trimmed.length < 3) return;
    setAsked(trimmed);
    startTransition(async () => {
      const r = await askAnything(trimmed, locations);
      setResult(r);
    });
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    run(question);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      run(question);
    }
  }

  const suggestions = locations.slice(0, 3).map((l, i) => {
    const templates = [`Is it icy at ${l.name} right now?`, `Any parking near ${l.name}?`, `What's the weather like at ${l.name}?`];
    return templates[i % templates.length];
  });

  return (
    <div className="relative overflow-hidden rounded-[32px] border border-white/15 bg-white/95 p-6 shadow-warm-lg backdrop-blur-xl sm:p-8">
      <div className="pointer-events-none absolute -left-20 -top-20 h-56 w-56 rounded-full bg-marigold/20 blur-3xl" />

      <form onSubmit={onSubmit} className="relative">
        <label htmlFor="ask-anything" className="flex items-center gap-2 text-sm font-semibold text-ink-soft">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-ink text-marigold-soft">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9.5 9a2.5 2.5 0 1 1 4 2c-.6.5-1.5 1-1.5 2.5M12 17.5h.01" />
            </svg>
          </span>
          Ask anything about a place
          {pending && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-marigold-soft border-t-marigold-deep" />}
        </label>
        <div className="relative mt-3">
          <textarea
            id="ask-anything"
            ref={textareaRef}
            rows={1}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="e.g. “Is it icy at Khardung La right now?” or “Any parking near Pangong Tso?”"
            className="thin-scroll w-full resize-none rounded-2xl border border-border-strong bg-paper py-4 pl-5 pr-5 text-[16px] leading-relaxed text-ink placeholder:text-ink-faint outline-none transition focus:border-marigold-deep focus:ring-4 focus:ring-marigold-soft/70"
          />
          {/* Visually hidden -- Enter submits (see onKeyDown); kept for
             a11y tools and password-manager-style form heuristics that
             expect a real submit control. */}
          <button type="submit" className="sr-only" disabled={pending || question.trim().length < 3}>
            Ask
          </button>
        </div>
        <p className="mt-2 text-right text-xs text-ink-faint">Press Enter to ask · Shift+Enter for a new line</p>
      </form>

      {!asked && (
        <div className="relative mt-4 flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setQuestion(s);
                run(s);
              }}
              className="rounded-full border border-border px-3 py-1.5 text-left text-xs font-medium text-ink-soft transition hover:-translate-y-0.5 hover:border-ink-faint hover:text-ink"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <AnimatePresence mode="wait">
        {asked && !pending && result && (
          <motion.div
            key={asked}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="relative mt-6 border-t border-border pt-6"
          >
            {result.matchedCondition ? (
              <div>
                {result.place && (
                  <Link
                    href={`/places/${result.place.location_id}`}
                    className="inline-flex items-center gap-1.5 rounded-full bg-paper-muted px-3 py-1 text-xs font-semibold text-ink-soft transition hover:text-ink"
                  >
                    About {result.place.name} <span aria-hidden>→</span>
                  </Link>
                )}
                <div className="mt-3 flex items-center gap-2">
                  <span className={clsx("h-2 w-2 rounded-full", TONE_DOT[freshnessTone(result.matchedCondition.state)])} />
                  <span className={clsx("text-[15px] font-bold", TONE_TEXT[freshnessTone(result.matchedCondition.state)])}>
                    {result.matchedCondition.display_name}: {freshnessLabel(result.matchedCondition.state)}
                  </span>
                </div>
                {result.matchedCondition.observed_at && (
                  <p className="mt-1 pl-4 text-xs text-ink-faint">{timeAgoLabel(result.matchedCondition.observed_at)}</p>
                )}
                {result.groundingObservation?.evidence && (
                  <p className="mt-4 text-[16px] leading-relaxed text-ink">&ldquo;{result.groundingObservation.evidence}&rdquo;</p>
                )}
                {result.groundingObservation && (
                  <p className="mt-2 text-xs text-ink-faint">Reported by {result.groundingObservation.guide_name}, local guide</p>
                )}
              </div>
            ) : result.fallbackObservations.length > 0 || result.fallbackPlaces.length > 0 ? (
              <div>
                <p className="text-sm text-ink-soft">
                  We couldn&rsquo;t pin that to one exact answer, but here&rsquo;s what&rsquo;s actually been reported that might help:
                </p>
                <div className="mt-4 space-y-2">
                  {result.fallbackObservations.map((o) => (
                    <Link
                      key={o.observation_id}
                      href={`/observations/${o.observation_id}`}
                      className="block rounded-xl px-3 py-2.5 text-sm text-ink-soft transition hover:bg-paper-muted"
                    >
                      <span className="text-ink">&ldquo;{o.evidence}&rdquo;</span>{" "}
                      <span className="text-ink-faint">
                        {o.nearest_place_name ? `— near ${o.nearest_place_name}, ` : "— "}
                        {timeAgoLabel(o.observed_at)}
                      </span>
                    </Link>
                  ))}
                  {result.fallbackPlaces.map((p) => (
                    <Link
                      key={p.location_id}
                      href={`/places/${p.location_id}`}
                      className="block rounded-xl px-3 py-2.5 text-sm font-medium text-ink transition hover:bg-paper-muted"
                    >
                      See everything about {p.name} →
                    </Link>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-ink-soft">
                We don&rsquo;t have a report that answers that yet — nothing here is guessed or generated, so we&rsquo;d
                rather say that than make something up. Try{" "}
                <Link href="/explore" className="font-semibold text-marigold-deep hover:underline">
                  exploring what we do know
                </Link>
                .
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
