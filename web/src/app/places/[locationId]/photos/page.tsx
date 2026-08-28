import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { content } from "@/lib/content";
import { PhotoGrid } from "@/components/PhotoGrid";
import { EmptyState } from "@/components/EmptyState";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locationId: string }>;
}): Promise<Metadata> {
  const { locationId } = await params;
  const place = await content.getLocation(locationId);
  return { title: place ? `Photos — ${place.name}` : "Photos" };
}

export default async function PlacePhotosPage({
  params,
}: {
  params: Promise<{ locationId: string }>;
}) {
  const { locationId } = await params;
  const place = await content.getLocation(locationId);
  if (!place) notFound();

  const photos = await content.listObservations({ locationId, hasPhoto: true, limit: 100 });

  return (
    <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8">
      <Link href={`/places/${place.location_id}`} className="text-sm font-semibold text-marigold-deep hover:underline">
        ← Back to {place.name}
      </Link>
      <h1 className="mt-4 font-heading text-3xl font-extrabold text-ink sm:text-4xl">Photos from {place.name}</h1>
      <p className="mt-2 text-ink-soft">{photos.total} captured by travellers and guides on the ground.</p>
      <div className="mt-10">
        {photos.items.length === 0 ? (
          <EmptyState title="No photos yet" body="Approved photos from this place will appear here." />
        ) : (
          <PhotoGrid observations={photos.items} />
        )}
      </div>
    </div>
  );
}
