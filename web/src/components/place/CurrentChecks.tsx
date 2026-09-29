import type { PublicLocationCategory } from "@/lib/content";
import { categoryStateLabel, categoryStateTone, formatDate } from "@/lib/content/freshness";
import { StatePill } from "./TrustTag";

/**
 * TrailMind-VERIFIED knowledge as a key-facts table (category / what a guide
 * confirmed / when, and whether it's still current) -- the reference guide's
 * "Key facts" layout. Only verified CategoryKnowledge ever reaches this
 * component (the backend drops pending items).
 */
export function VerifiedKnowledge({ categories }: { categories: PublicLocationCategory[] }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-paper-elevated">
      <div className="hidden grid-cols-[190px_1fr_190px] gap-6 border-b border-border bg-paper-muted/60 px-5 py-2.5 text-[10px] font-bold uppercase tracking-[0.12em] text-ink-faint sm:grid">
        <span>Category</span>
        <span>What a guide confirmed</span>
        <span>Checked</span>
      </div>
      <ul className="divide-y divide-border">
        {categories.flatMap((category) =>
          category.verified_knowledge.map((k, i) => (
            <li key={k.knowledge_id} className="grid gap-2 px-5 py-4 sm:grid-cols-[190px_1fr_190px] sm:gap-6">
              <div>
                {i === 0 && (
                  <>
                    <p className="font-heading text-[15px] font-bold text-ink">{category.display_name}</p>
                    <div className="mt-1">
                      <StatePill tone={categoryStateTone(category.state)}>{categoryStateLabel(category.state)}</StatePill>
                    </div>
                  </>
                )}
              </div>
              <p className="text-[15px] leading-relaxed text-ink">{k.knowledge_text}</p>
              <p className="text-xs leading-relaxed text-ink-faint">
                {formatDate(k.last_verified_at)}
                <br />
                <span className={k.fresh ? "font-semibold text-ok" : "font-semibold text-fix"}>
                  {k.fresh ? "Still current" : "Due for a re-check"}
                </span>
              </p>
            </li>
          )),
        )}
      </ul>
    </div>
  );
}
