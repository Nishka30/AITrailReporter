import type { PlaceResearchSummary } from "@/lib/content";
import { formatDate } from "@/lib/content/freshness";

/** Which research field (if any) the page intro already used as its lede. */
export type LedeField = "description" | "known_for" | null;

export function hasReferenceContent(summary: PlaceResearchSummary | null, lede: LedeField): boolean {
  if (!summary) return false;
  return Boolean(
    (lede !== "description" && summary.description) ||
      (lede !== "known_for" && summary.known_for) ||
      summary.practical_info ||
      summary.warnings.length ||
      summary.important_facts.length ||
      summary.highlights.length ||
      summary.things_to_do.length,
  );
}

/**
 * "Place reference" -- background from web research ONLY (the backend's
 * already-validated PlaceResearchSummary), laid out as quiet reading text
 * with no freshness pills or guide names so it can never be mistaken for a
 * live report. The page renders it on its own muted band, the reference
 * guide's separation between dated reports and planning foundations.
 */
export function ResearchSummarySection({ summary, lede }: { summary: PlaceResearchSummary; lede: LedeField }) {
  const description = lede !== "description" ? summary.description : null;
  const knownFor = lede !== "known_for" ? summary.known_for : null;

  return (
    <div className="space-y-10">
      <div className="grid gap-8 md:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4 text-[15px] leading-[1.8] text-ink-soft">
          {description && <p className="text-base text-ink">{description}</p>}
          {knownFor && <p>{knownFor}</p>}
          {summary.highlights.length > 0 && (
            <div>
              <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">Known for</h3>
              <ul className="mt-2 flex flex-wrap gap-2">
                {summary.highlights.map((h) => (
                  <li key={h} className="rounded-full border border-border bg-paper-elevated px-3 py-1 text-[13px] font-medium text-ink-soft">
                    {h}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {summary.practical_info && (
            <div>
              <h3 className="font-heading text-base font-bold text-ink">Good to know before you go</h3>
              <p className="mt-1.5">{summary.practical_info}</p>
            </div>
          )}
        </div>

        <div className="space-y-4">
          {summary.important_facts.length > 0 && (
            <div className="rounded-xl border border-border bg-paper-elevated p-5">
              <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">Key facts</h3>
              <ul className="mt-3 space-y-2.5">
                {summary.important_facts.map((fact) => (
                  <li key={fact} className="flex gap-2.5 text-sm leading-relaxed text-ink">
                    <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-ink-faint" />
                    {fact}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {summary.warnings.length > 0 && (
            <div className="rounded-xl border border-fix/25 bg-fix-soft/60 p-5">
              <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-fix">Important to know</h3>
              <ul className="mt-3 space-y-2">
                {summary.warnings.map((w) => (
                  <li key={w} className="text-sm leading-relaxed text-ink">
                    {w}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {summary.things_to_do.length > 0 && (
        <div>
          <h3 className="font-heading text-lg font-bold text-ink">Make the time your own</h3>
          <ol className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {summary.things_to_do.map((item, i) => (
              <li key={item} className="flex gap-3 rounded-xl border border-border bg-paper-elevated p-4 text-sm leading-relaxed text-ink">
                <span className="font-heading text-sm font-extrabold text-marigold-deep">{String(i + 1).padStart(2, "0")}</span>
                {item}
              </li>
            ))}
          </ol>
        </div>
      )}

      {summary.researched_at && (
        <p className="text-xs text-ink-faint">
          Researched {formatDate(summary.researched_at)} from public web sources (listed under Sources). Not checked on the ground
          by a TrailMind guide.
        </p>
      )}
    </div>
  );
}
