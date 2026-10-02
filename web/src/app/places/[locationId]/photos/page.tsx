import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { content } from "@/lib/content";
import { PhotoGrid } from "@/components/PhotoGrid";
import { EmptyState } from "@/components/EmptyState";
import { Breadcrumb } from "@/components/guide/primitives";

export async function generateMetadata({ params }: { params: Promise<{ locationId: string }> }): Promise<Metadata> {
  const { locationId } = await params;
  const place = await content.getLocation(locationId);
  return { title: place ? `Photos — ${place.name}` : "Photos" };
}

export default async function PlacePhotosPage({ params }: { params: Promise<{ locationId: string }> }) {
  const { locationId } = await params;
  const place = await content.getLocation(locationId);
  if (!place) notFound();
  const photos = await content.listObservations({ locationId, hasPhoto: true, limit: 100 });

  return (
    <div className="page pb-20 pt-7">
      <Breadcrumb items={[{ label: "Explore", href: "/explore" }, { label: place.name, href: `/places/${place.location_id}` }, { label: "Photos" }]} />
      <div className="mt-3 max-w-[720px]">
        <p className="eyebrow">A closer look</p>
        <h1 className="mt-3 text-[40px] font-bold leading-[1.1] tracking-[-0.035em] text-ink sm:text-[46px]">Photos from {place.name}</h1>
        <p className="mt-3 text-[17px] text-ink-soft">
          {photos.total} photo{photos.total === 1 ? "" : "s"} attached to dated guide reports.
        </p>
      </div>
      <div className="mt-10">
        {photos.items.length === 0 ? (
          <EmptyState title="No photos yet" body="Photos from reviewed guide reports will appear here." />
        ) : (
          <PhotoGrid observations={photos.items} />
        )}
      </div>
    </div>
  );
}
