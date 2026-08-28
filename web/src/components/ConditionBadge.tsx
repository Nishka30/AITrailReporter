import type { PublicConditionState } from "@/lib/content";
import { freshnessLabel, freshnessTone, timeAgoLabel } from "@/lib/content/freshness";
import clsx from "clsx";

const TONE_STYLES: Record<string, string> = {
  good: "bg-gradient-to-br from-ok-soft to-ok-soft/40 text-ok border-ok/15",
  warn: "bg-gradient-to-br from-marigold-soft to-marigold-soft/40 text-marigold-deep border-marigold/25",
  bad: "bg-gradient-to-br from-fix-soft to-fix-soft/40 text-fix border-fix/15",
  neutral: "bg-gradient-to-br from-paper-muted to-paper-muted/40 text-ink-faint border-border",
};

const DOT_STYLES: Record<string, string> = {
  good: "bg-ok shadow-[0_0_0_3px_rgba(31,111,74,0.15)]",
  warn: "bg-marigold-deep shadow-[0_0_0_3px_rgba(201,130,31,0.18)]",
  bad: "bg-fix shadow-[0_0_0_3px_rgba(184,57,31,0.18)]",
  neutral: "bg-ink-faint shadow-[0_0_0_3px_rgba(138,125,112,0.15)]",
};

export function ConditionBadge({ condition, large = false }: { condition: PublicConditionState; large?: boolean }) {
  const tone = freshnessTone(condition.state);
  const isAlert = condition.safety_critical && (tone === "bad" || tone === "warn");

  return (
    <div
      className={clsx(
        "rounded-2xl border p-4 backdrop-blur-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-warm",
        TONE_STYLES[tone],
        isAlert && "ring-2 ring-fix/25",
        large ? "min-w-[220px]" : "min-w-[180px]",
      )}
    >
      <div className="flex items-center gap-2">
        <span className={clsx("h-2 w-2 shrink-0 rounded-full", DOT_STYLES[tone])} />
        <p className="text-sm font-semibold text-ink">{condition.display_name}</p>
        {condition.safety_critical && (
          <span className="ml-auto rounded-full bg-ink/5 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-ink-faint">
            Safety
          </span>
        )}
      </div>
      <p className="mt-2 text-sm font-medium leading-snug">{freshnessLabel(condition.state)}</p>
      <p className="mt-1 text-xs text-ink-faint">{timeAgoLabel(condition.observed_at)}</p>
    </div>
  );
}
