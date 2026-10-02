import type { PlaceResearchSummary } from "@/lib/content";

function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

/**
 * Where everything on the page came from: the guides whose approved reports
 * appear above, and the web sources behind the background research.
 */
export function SourcesAndContributors({
  summary,
  guideNames,
}: {
  summary: PlaceResearchSummary | null;
  guideNames: string[];
}) {
  const sources = summary?.source_urls ?? [];
  return (
    <div className="grid gap-8 rounded-xl border border-border bg-paper-elevated p-6 sm:grid-cols-2 sm:p-8">
      {guideNames.length > 0 && (
        <div>
          <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">Guide reports from</h3>
          <p className="mt-2 text-sm leading-relaxed text-ink">{guideNames.join(", ")}</p>
          <p className="mt-2 text-xs leading-relaxed text-ink-faint">
            Each report is reviewed before it appears here. A recent report is a record of one visit, not a guarantee.
          </p>
        </div>
      )}
      {sources.length > 0 && (
        <div>
          <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">Background research sources</h3>
          <ul className="mt-2 space-y-1.5">
            {sources.map((url, i) => (
              <li key={url} className="text-sm">
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-ink-soft underline decoration-dotted underline-offset-2 hover:text-accent-deep"
                >
                  {summary?.source_titles[i] || hostnameOf(url)}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
