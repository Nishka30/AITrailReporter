import type { Metadata } from "next";
import { content } from "@/lib/content";
import { coverPhotoFor } from "@/lib/content/coverPhoto";
import { SearchBar } from "@/components/SearchBar";
import { LocationCard } from "@/components/LocationCard";
import { ObservationCard } from "@/components/ObservationCard";
import { EmptyState } from "@/components/EmptyState";

export const metadata: Metadata = { title: "Search" };

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = (q ?? "").trim();
  const result = query ? await content.search(query) : null;

  const locationsWithPhotos = result
    ? await Promise.all(result.locations.map(async (l) => ({ location: l, photo: await coverPhotoFor(l.location_id) })))
    : [];

  return (
    <div className="mx-auto max-w-5xl px-5 py-14 sm:px-8">
      <h1 className="font-heading text-3xl font-extrabold text-ink sm:text-4xl">Search</h1>
      <div className="mt-6 max-w-xl">
        <SearchBar initialQuery={query} />
      </div>

      {!query && (
        <p className="mt-10 text-sm text-ink-soft">Search for a place, trail, or condition — try &ldquo;snow&rdquo; or &ldquo;Leh&rdquo;.</p>
      )}

      {result && (
        <div className="mt-12 space-y-14">
          {result.locations.length === 0 && result.observations.length === 0 ? (
            <EmptyState title={`No results for "${query}"`} body="Try a different place name or condition." />
          ) : (
            <>
              {locationsWithPhotos.length > 0 && (
                <section>
                  <h2 className="font-heading text-xl font-bold text-ink">Places</h2>
                  <div className="mt-5 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                    {locationsWithPhotos.map(({ location, photo }) => (
                      <LocationCard key={location.location_id} location={location} coverPhotoUrl={photo} />
                    ))}
                  </div>
                </section>
              )}
              {result.observations.length > 0 && (
                <section>
                  <h2 className="font-heading text-xl font-bold text-ink">Reports</h2>
                  <div className="mt-5 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                    {result.observations.map((o) => (
                      <ObservationCard key={o.observation_id} observation={o} />
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
