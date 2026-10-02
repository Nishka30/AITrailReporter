import clsx from "clsx";

/**
 * The ONE visual marker for where a piece of Location-page content comes
 * from. Every section carries exactly one, so the three trust layers never
 * blur together:
 *   research -- background from web research (never verified by a guide)
 *   verified -- CategoryKnowledge a guide's approved report confirmed
 *   live     -- individual dated guide reports / current answers
 */
export type TrustKind = "research" | "verified" | "live";

const STYLES: Record<TrustKind, { label: string; className: string; icon: React.ReactNode }> = {
  research: {
    label: "Background · web research",
    className: "bg-info-soft text-info",
    icon: <path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2V5ZM4 19a2 2 0 0 1 2-2h13" />,
  },
  verified: {
    label: "Verified by TrailMind guides",
    className: "bg-ok-soft text-ok",
    icon: <path d="M20 6 9 17l-5-5" />,
  },
  live: {
    label: "Local checks · guide reports",
    className: "bg-accent-soft text-accent-deep",
    icon: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
      </>
    ),
  },
};

export function TrustTag({ kind, className }: { kind: TrustKind; className?: string }) {
  const style = STYLES[kind];
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]",
        style.className,
        className,
      )}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        {style.icon}
      </svg>
      {style.label}
    </span>
  );
}

const EYEBROW_TONE: Record<TrustKind | "neutral", string> = {
  research: "text-info",
  verified: "text-ok",
  live: "text-accent-deep",
  neutral: "text-ink-faint",
};

/**
 * Field-guide section header: a small uppercase eyebrow naming what KIND
 * of content follows (coloured by trust layer, with its icon), the heading,
 * and one line of context.
 */
export function PlaceSectionHeading({
  kind,
  eyebrow,
  title,
  intro,
  aside,
}: {
  kind?: TrustKind;
  eyebrow: string;
  title: string;
  intro?: React.ReactNode;
  aside?: React.ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-[650px]">
        <p className={clsx("flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em]", EYEBROW_TONE[kind ?? "neutral"])}>
          {kind && (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              {STYLES[kind].icon}
            </svg>
          )}
          {eyebrow}
        </p>
        <h2 className="mt-2 font-heading text-[26px] font-extrabold leading-tight tracking-tight text-ink sm:text-3xl">{title}</h2>
        {intro && <p className="mt-2 text-[15px] leading-[1.75] text-ink-soft">{intro}</p>}
      </div>
      {aside}
    </div>
  );
}

export const TONE_DOT: Record<string, string> = {
  good: "bg-ok",
  warn: "bg-marigold-deep",
  bad: "bg-fix",
  neutral: "bg-ink-faint",
};

export const TONE_PILL: Record<string, string> = {
  good: "bg-ok-soft text-ok",
  warn: "bg-marigold-soft text-marigold-deep",
  bad: "bg-fix-soft text-fix",
  neutral: "bg-paper-muted text-ink-faint",
};

export function StatePill({ tone, children }: { tone: string; children: React.ReactNode }) {
  return (
    <span className={clsx("inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold", TONE_PILL[tone])}>
      <span className={clsx("h-1.5 w-1.5 rounded-full", TONE_DOT[tone])} />
      {children}
    </span>
  );
}
