import type { Metadata } from "next";
import { content } from "@/lib/content";
import { SearchBar } from "@/components/SearchBar";
import { EmptyState } from "@/components/EmptyState";
import { Breadcrumb } from "@/components/guide/primitives";
import { PlaceCard } from "@/components/guide/PlaceCards";
import { ReportCard } from "@/components/guide/ReportCard";
import { stateByAge } from "@/lib/content/locationPage";

export const metadata: Metadata = { title: "Search" };

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  const query = (q ?? "").trim();
  const result = query ? await content.search(query) : null;
  const places = result ? [...result.locations].sort((a, b) => Number(Boolean(b.is_area_hub)) - Number(Boolean(a.is_area_hub))) : [];

  return (
    <div className="page pb-20 pt-7">
      <Breadcrumb items={[{ label: "Home", href: "/" }, { label: "Search" }]} />
      <div className="mt-3 max-w-[720px]">
        <p className="eyebrow">Places, reports and conditions</p>
        <h1 className="mt-3 text-[40px] font-bold leading-[1.08] tracking-[-0.035em] text-ink sm:text-[50px]">
          {query ? <>Results for &ldquo;{query}&rdquo;</> : "Search"}
        </h1>
        <div className="mt-6">
          <SearchBar initialQuery={query} />
        </div>
        {!query && (
          <p className="mt-5 text-[15.5px] text-ink-soft">
            Try a place name like &ldquo;Lukla&rdquo;, or a condition like &ldquo;snow&rdquo; or &ldquo;Wi-Fi&rdquo;.
          </p>
        )}
      </div>

      {result && (
        <div className="mt-14 space-y-16">
          {places.length === 0 && result.observations.length === 0 ? (
            <EmptyState title={`Nothing matches "${query}" yet`} body="Try a different place name or condition — or ask a local guide." />
          ) : (
            <>
              {places.length > 0 && (
                <section>
                  <div className="mb-6 flex items-end justify-between border-b border-border-soft pb-4">
                    <h2 className="text-[24px] font-bold tracking-[-0.02em] text-ink">Places</h2>
                    <span className="text-[13px] text-ink-faint">
                      {places.length} match{places.length === 1 ? "" : "es"}
                    </span>
                  </div>
                  <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                    {places.map((p) => (
                      <div key={p.location_id} className="flex">
                        <PlaceCard place={p} />
                      </div>
                    ))}
                  </div>
                </section>
              )}
              {result.observations.length > 0 && (
                <section>
                  <div className="mb-6 flex items-end justify-between border-b border-border-soft pb-4">
                    <h2 className="text-[24px] font-bold tracking-[-0.02em] text-ink">Field reports</h2>
                    <span className="text-[13px] text-ink-faint">
                      {result.observations.length} match{result.observations.length === 1 ? "" : "es"}
                    </span>
                  </div>
                  <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                    {result.observations.map((o) => (
                      <div key={o.observation_id} className="flex">
                        <ReportCard check={{ observation: o, label: o.category_display_name ?? o.display_name, state: stateByAge(o.observed_at) }} />
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
