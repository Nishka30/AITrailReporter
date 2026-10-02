import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { content } from "@/lib/content";
import { EmptyState } from "@/components/EmptyState";
import { Breadcrumb } from "@/components/guide/primitives";
import { ReportCard } from "@/components/guide/ReportCard";
import { buildLocalChecks } from "@/lib/content/locationPage";

export async function generateMetadata({ params }: { params: Promise<{ locationId: string }> }): Promise<Metadata> {
  const { locationId } = await params;
  const place = await content.getLocation(locationId);
  return { title: place ? `Reports — ${place.name}` : "Reports" };
}

export default async function PlaceStoriesPage({ params }: { params: Promise<{ locationId: string }> }) {
  const { locationId } = await params;
  const place = await content.getLocation(locationId);
  if (!place) notFound();
  const observations = await content.listObservations({ locationId, limit: 100 });
  const checks = buildLocalChecks(observations.items, place.conditions, place.categories);

  return (
    <div className="page pb-20 pt-7">
      <Breadcrumb items={[{ label: "Explore", href: "/explore" }, { label: place.name, href: `/places/${place.location_id}` }, { label: "All reports" }]} />
      <div className="mt-3 max-w-[720px]">
        <p className="eyebrow">The local field notebook</p>
        <h1 className="mt-3 text-[40px] font-bold leading-[1.1] tracking-[-0.035em] text-ink sm:text-[46px]">Every report from {place.name}</h1>
        <p className="mt-3 text-[17px] text-ink-soft">
          {observations.total} reviewed report{observations.total === 1 ? "" : "s"}, newest first. Older reports of the same kind are marked as older.
        </p>
      </div>
      <div className="mt-10">
        {checks.length === 0 ? (
          <EmptyState title="No reports yet" body="Reviewed guide reports from this place will appear here." />
        ) : (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {checks.map((c) => (
              <div key={c.observation.observation_id} className="flex">
                <ReportCard check={c} showPlace={place.name} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
