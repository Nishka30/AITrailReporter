import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { content } from "@/lib/content";
import { ObservationCard } from "@/components/ObservationCard";
import { EmptyState } from "@/components/EmptyState";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locationId: string }>;
}): Promise<Metadata> {
  const { locationId } = await params;
  const place = await content.getLocation(locationId);
  return { title: place ? `Reports — ${place.name}` : "Reports" };
}

export default async function PlaceStoriesPage({
  params,
}: {
  params: Promise<{ locationId: string }>;
}) {
  const { locationId } = await params;
  const place = await content.getLocation(locationId);
  if (!place) notFound();

  const observations = await content.listObservations({ locationId, limit: 100 });

  return (
    <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8">
      <Link href={`/places/${place.location_id}`} className="text-sm font-semibold text-marigold-deep hover:underline">
        ← Back to {place.name}
      </Link>
      <h1 className="mt-4 font-heading text-3xl font-extrabold text-ink sm:text-4xl">Every report from {place.name}</h1>
      <p className="mt-2 text-ink-soft">{observations.total} report{observations.total === 1 ? "" : "s"}, newest first.</p>
      <div className="mt-10">
        {observations.items.length === 0 ? (
          <EmptyState title="No reports yet" body="Approved reports from this place will appear here." />
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {observations.items.map((o) => (
              <ObservationCard key={o.observation_id} observation={o} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
