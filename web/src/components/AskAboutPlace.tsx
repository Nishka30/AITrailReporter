"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import type { PublicConditionState, PublicObservation } from "@/lib/content";
import { askAboutPlace } from "@/lib/content/ask";
import { freshnessLabel, freshnessTone, timeAgoLabel } from "@/lib/content/freshness";
import clsx from "clsx";

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

export function AskAboutPlace({
  placeName,
  conditions,
  observations,
}: {
  placeName: string;
  conditions: PublicConditionState[];
  observations: PublicObservation[];
}) {
  const [query, setQuery] = useState("");
  const trimmed = query.trim();

  const result = useMemo(
    () => (trimmed.length >= 3 ? askAboutPlace(trimmed, conditions, observations) : null),
    [trimmed, conditions, observations],
  );

  const suggestions = conditions.slice(0, 4).map((c) => c.display_name);

  return (
    <div className="relative overflow-hidden rounded-[28px] border border-border/70 bg-paper-elevated p-6 shadow-warm-lg sm:p-8">
      <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-marigold-soft/50 blur-3xl" />
      <div className="relative flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-ink text-marigold-soft">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9.5 9a2.5 2.5 0 1 1 4 2c-.6.5-1.5 1-1.5 2.5M12 17.5h.01" />
            <circle cx="12" cy="12" r="9.5" />
          </svg>
        </span>
        <p className="font-heading text-lg font-bold text-ink">Ask about {placeName}</p>
      </div>
      <p className="relative mt-2 text-sm text-ink-soft">
        We&rsquo;ll answer straight from what&rsquo;s actually been reported here — never a guess.
      </p>

      <div className="relative mt-5">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. “Is it icy right now?” or “Any parking?”"
          className="w-full rounded-2xl border border-border-strong bg-paper py-3.5 pl-5 pr-5 text-[15px] text-ink placeholder:text-ink-faint outline-none transition focus:border-marigold-deep focus:ring-4 focus:ring-marigold-soft/70"
        />
      </div>

      {!trimmed && suggestions.length > 0 && (
        <div className="relative mt-4 flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setQuery(`${s}?`)}
              className="rounded-full border border-border px-3 py-1.5 text-xs font-medium text-ink-soft transition hover:-translate-y-0.5 hover:border-ink-faint hover:text-ink active:translate-y-0"
            >
              {s}?
            </button>
          ))}
        </div>
      )}

      <AnimatePresence mode="wait">
        {result && (
          <motion.div
            key={result.matchedCondition?.knowledge_type ?? "none"}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className="relative mt-6 border-t border-border pt-6"
          >
            {result.matchedCondition ? (
              <div>
                <div className="flex items-center gap-2">
                  <span className={clsx("h-2 w-2 rounded-full", TONE_DOT[freshnessTone(result.matchedCondition.state)])} />
                  <span className={clsx("text-[15px] font-bold", TONE_TEXT[freshnessTone(result.matchedCondition.state)])}>
                    {result.matchedCondition.display_name}: {freshnessLabel(result.matchedCondition.state)}
                  </span>
                </div>
                {result.matchedCondition.observed_at && (
                  <p className="mt-1.5 pl-4 text-xs text-ink-faint">{timeAgoLabel(result.matchedCondition.observed_at)}</p>
                )}

                {result.groundingObservation?.evidence && (
                  <p className="mt-4 text-[16px] leading-relaxed text-ink">
                    &ldquo;{result.groundingObservation.evidence}&rdquo;
                  </p>
                )}
                {result.groundingObservation && (
                  <p className="mt-2 text-xs text-ink-faint">
                    Reported by {result.groundingObservation.guide_name}, local guide
                  </p>
                )}

                {result.supportingObservations.length > 0 && (
                  <div className="mt-5 space-y-1">
                    <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Other reports that mention this</p>
                    {result.supportingObservations.map((o) => (
                      <Link
                        key={o.observation_id}
                        href={`/observations/${o.observation_id}`}
                        className="block rounded-xl px-3 py-2 text-sm text-ink-soft transition hover:bg-paper-muted"
                      >
                        &ldquo;{o.evidence}&rdquo; <span className="text-ink-faint">— {timeAgoLabel(o.observed_at)}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-ink-soft">
                We don&rsquo;t have a report that answers that yet. Browse everything we do know about{" "}
                {placeName} below.
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
