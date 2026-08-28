import Link from "next/link";
import clsx from "clsx";
import { content } from "@/lib/content";
import { LocationCard } from "@/components/LocationCard";
import { ObservationCard } from "@/components/ObservationCard";
import { EmptyState } from "@/components/EmptyState";
import { DynamicMap } from "@/components/DynamicMap";
import { coverPhotoFor } from "@/lib/content/coverPhoto";
import { Reveal, RevealGroup, RevealItem } from "@/components/motion/Reveal";
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

  const locationsWithPhotos =
    view === "list"
      ? await Promise.all(locations.slice(0, 24).map(async (l) => ({ location: l, photo: await coverPhotoFor(l.location_id) })))
      : [];

  const hasActiveFilter = Boolean(sp.knowledge_type || sp.has_photos || sp.has_voice || sp.safety);

  return (
    <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8">
      <Reveal className="max-w-2xl">
        <h1 className="font-heading text-4xl font-extrabold tracking-tight text-ink sm:text-5xl">Explore</h1>
        <p className="mt-4 text-lg text-ink-soft">
          Every place currently being reported on, and what people have noticed lately. Start
          broad, or filter down to what you actually need to know.
        </p>
      </Reveal>

      {/* Filter chips */}
      <div className="mt-8 flex flex-wrap gap-2">
        <FilterChip href={buildHref(sp, { has_photos: sp.has_photos === "true" ? undefined : "true" })} active={sp.has_photos === "true"}>
          Has photos
        </FilterChip>
        <FilterChip href={buildHref(sp, { has_voice: sp.has_voice === "true" ? undefined : "true" })} active={sp.has_voice === "true"}>
          Voice stories
        </FilterChip>
        <FilterChip href={buildHref(sp, { safety: sp.safety === "true" ? undefined : "true" })} active={sp.safety === "true"}>
          Safety-critical
        </FilterChip>
        <span className="mx-1 my-auto h-4 w-px bg-border" />
        {knowledgeTypes.map((kt) => (
          <FilterChip
            key={kt.knowledge_type}
            href={buildHref(sp, { knowledge_type: sp.knowledge_type === kt.knowledge_type ? undefined : kt.knowledge_type })}
            active={sp.knowledge_type === kt.knowledge_type}
          >
            {kt.display_name}
          </FilterChip>
        ))}
        {hasActiveFilter && (
          <Link href="/explore" className="ml-1 my-auto text-xs font-semibold text-ink-faint underline-offset-2 hover:underline">
            Clear filters
          </Link>
        )}
      </div>

      {/* Places: list / map toggle */}
      <section className="mt-16">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="font-heading text-2xl font-bold tracking-tight text-ink">Places</h2>
          <div className="flex overflow-hidden rounded-full border border-border bg-paper-elevated p-0.5 text-sm font-medium shadow-warm">
            <Link
              href={buildHref(sp, { view: undefined })}
              className={clsx("rounded-full px-4 py-1.5 transition", view === "list" ? "bg-ink text-paper" : "text-ink-soft hover:text-ink")}
            >
              List
            </Link>
            <Link
              href={buildHref(sp, { view: "map" })}
              className={clsx("rounded-full px-4 py-1.5 transition", view === "map" ? "bg-ink text-paper" : "text-ink-soft hover:text-ink")}
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
          <RevealGroup className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {locationsWithPhotos.map(({ location, photo }) => (
              <RevealItem key={location.location_id}>
                <LocationCard location={location} coverPhotoUrl={photo} />
              </RevealItem>
            ))}
          </RevealGroup>
        )}
      </section>

      {/* Matching observations */}
      <section className="mt-16">
        <h2 className="font-heading text-2xl font-bold tracking-tight text-ink">
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
          <RevealGroup className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filteredObservations.map((o) => (
              <RevealItem key={o.observation_id}>
                <ObservationCard observation={o} />
              </RevealItem>
            ))}
          </RevealGroup>
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
        "rounded-full border px-3.5 py-1.5 text-sm font-medium transition-all duration-200",
        active
          ? "border-ink bg-ink text-paper shadow-warm"
          : "border-border text-ink-soft hover:-translate-y-0.5 hover:border-ink-faint hover:text-ink",
      )}
    >
      {children}
    </Link>
  );
}
