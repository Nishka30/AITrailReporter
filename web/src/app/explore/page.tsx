import Link from "next/link";
import clsx from "clsx";
import { content } from "@/lib/content";
import { EmptyState } from "@/components/EmptyState";
import { DynamicMap } from "@/components/DynamicMap";
import { PlaceCard } from "@/components/guide/PlaceCards";
import { ReportCard } from "@/components/guide/ReportCard";
import { Breadcrumb } from "@/components/guide/primitives";
import { stateByAge } from "@/lib/content/locationPage";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Explore" };

interface Search {
  knowledge_type?: string;
  has_photos?: string;
  has_voice?: string;
  safety?: string;
  view?: string;
}

function buildHref(current: Search, patch: Partial<Search>) {
  const merged: Search = { ...current, ...patch };
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(merged)) {
    if (value) params.set(key, value);
  }
  const qs = params.toString();
  return qs ? `/explore?${qs}` : "/explore";
}

export default async function ExplorePage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const sp = await searchParams;
  const view = sp.view === "map" ? "map" : "list";

  const [locations, knowledgeTypes, observations] = await Promise.all([
    content.listLocations(100),
    content.listKnowledgeTypes(),
    content.listObservations({
      knowledgeType: sp.knowledge_type,
      hasPhoto: sp.has_photos === "true" ? true : undefined,
      hasAudio: sp.has_voice === "true" ? true : undefined,
      limit: 40,
    }),
  ]);

  const filteredObservations = sp.safety === "true"
    ? observations.items.filter((o) => o.safety_critical)
    : observations.items;

  const hubsFirst = [...locations].sort((a, b) => Number(Boolean(b.is_area_hub)) - Number(Boolean(a.is_area_hub)));

  const hasActiveFilter = Boolean(sp.knowledge_type || sp.has_photos || sp.has_voice || sp.safety);

  return (
    <div className="page pb-20 pt-7">
      <Breadcrumb items={[{ label: "Home", href: "/" }, { label: "Explore" }]} />
      <div className="mt-3 max-w-[720px]">
        <p className="eyebrow">Every place we cover</p>
        <h1 className="mt-3 text-[40px] font-bold leading-[1.08] tracking-[-0.035em] text-ink sm:text-[50px]">Explore</h1>
        <p className="mt-4 text-[18px] leading-[1.75] text-ink-soft">
          Every place guides report on, and what they have noticed lately. Start broad, or filter down to what you need to know.
        </p>
      </div>

      {/* Filters */}
      <div className="mt-10 space-y-5">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-ink-faint">Filters</p>
          {hasActiveFilter && (
            <Link
              href="/explore"
              className="rounded-full border border-border px-3 py-1 text-xs font-semibold text-ink-soft transition hover:border-ink-faint hover:text-ink"
            >
              Clear filters
            </Link>
          )}
        </div>

        <div className="rail -mx-5 flex gap-2 overflow-x-auto px-5 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
          <FilterChip href={buildHref(sp, { has_photos: sp.has_photos === "true" ? undefined : "true" })} active={sp.has_photos === "true"}>
            <CameraIcon /> Has photos
          </FilterChip>
          <FilterChip href={buildHref(sp, { has_voice: sp.has_voice === "true" ? undefined : "true" })} active={sp.has_voice === "true"}>
            <MicIcon /> Voice stories
          </FilterChip>
          <FilterChip href={buildHref(sp, { safety: sp.safety === "true" ? undefined : "true" })} active={sp.safety === "true"}>
            <WarningIcon /> Safety-critical
          </FilterChip>
        </div>

        {knowledgeTypes.length > 0 && (
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.15em] text-ink-faint">Category</p>
            <div className="rail -mx-5 flex gap-2 overflow-x-auto px-5 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
              {knowledgeTypes.map((kt) => (
                <FilterChip
                  key={kt.knowledge_type}
                  href={buildHref(sp, { knowledge_type: sp.knowledge_type === kt.knowledge_type ? undefined : kt.knowledge_type })}
                  active={sp.knowledge_type === kt.knowledge_type}
                >
                  {kt.display_name}
                </FilterChip>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Places: list / map toggle */}
      <section className="mt-16">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-[27px] font-bold tracking-[-0.025em] text-ink">Places</h2>
          <div className="flex overflow-hidden rounded-[22px] border border-border-soft bg-white p-0.5 text-sm">
            <Link
              href={buildHref(sp, { view: undefined })}
              className={clsx("rounded-full px-4 py-1.5 transition", view === "list" ? "bg-pill text-white" : "text-ink-soft hover:text-ink")}
            >
              List
            </Link>
            <Link
              href={buildHref(sp, { view: "map" })}
              className={clsx("rounded-full px-4 py-1.5 transition", view === "map" ? "bg-pill text-white" : "text-ink-soft hover:text-ink")}
            >
              Map
            </Link>
          </div>
        </div>

        {locations.length === 0 ? (
          <EmptyState title="No places yet" body="Places appear here once they have at least one approved report." />
        ) : view === "map" ? (
          <DynamicMap
            pins={locations.map((l) => ({ id: l.location_id, name: l.name, latitude: l.latitude, longitude: l.longitude, href: `/places/${l.location_id}` }))}
            height={480}
          />
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {hubsFirst.slice(0, 24).map((location) => (
              <div key={location.location_id} className="flex">
                <PlaceCard place={location} />
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Matching observations */}
      <section id="reports" className="mt-16 scroll-mt-6">
        <h2 className="text-[27px] font-bold tracking-[-0.025em] text-ink">
          {hasActiveFilter ? "Matching reports" : "Latest reports"}
        </h2>
        {filteredObservations.length === 0 ? (
          <div className="mt-6">
            <EmptyState
              title="Nothing matches yet"
              body="Try clearing a filter, or check back soon — new reports come in as guides file them."
            />
          </div>
        ) : (
          <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {filteredObservations.map((o) => (
              <div key={o.observation_id} className="flex">
                <ReportCard check={{ observation: o, label: o.category_display_name ?? o.display_name, state: stateByAge(o.observed_at) }} />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function FilterChip({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className={clsx(
        "flex h-[40px] shrink-0 items-center gap-1.5 rounded-[22px] border px-4 text-[14px] transition",
        active ? "border-pill bg-pill text-white" : "border-border-soft bg-white text-ink-meta hover:border-border-strong hover:text-ink",
      )}
    >
      {children}
    </Link>
  );
}

function CameraIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 opacity-70">
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2Z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 opacity-70">
      <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z" />
      <path d="M19 11a7 7 0 0 1-14 0M12 18v3" />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 opacity-70">
      <path d="M12 9v4M12 17h.01M10.3 3.9 1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
    </svg>
  );
}
