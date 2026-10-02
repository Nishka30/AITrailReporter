import Link from "next/link";
import type { PublicLocationSummary } from "@/lib/content";
import { formatDate } from "@/lib/content/freshness";
import { cleanDescription, formatMeters, placeTypeOf, themesOf } from "@/lib/content/guide";
import { CardEyebrow, TextLink } from "./primitives";
import { Icon, type IconName } from "./Icons";
import { MapTile } from "./MapTile";

const THEME_ICON: Record<string, IconName> = {
  lodging: "bed",
  food_drink: "cup",
  transport: "plane",
  culture_heritage: "temple",
  religious: "temple",
  practical: "shop",
  shopping: "shop",
  services: "shop",
  finance: "shop",
  scenic_spot: "mountain",
  nature: "mountain",
  viewpoint: "mountain",
  photography: "camera",
  trekking: "boots",
  adventure: "boots",
};

export function iconForPlace(place: PublicLocationSummary): IconName {
  for (const t of themesOf(place)) if (THEME_ICON[t.slug]) return THEME_ICON[t.slug];
  return "pin";
}

function CheckPanel({ place }: { place: PublicLocationSummary }) {
  if (place.last_activity_at) {
    return (
      <div className="rounded-[6px] bg-ok-soft px-4 py-3.5 text-[13.5px] leading-[1.7] text-ok">
        <p className="flex items-center gap-2 font-semibold text-ink">
          <Icon name="clock" size={15} className="text-ok" />
          Latest report nearby {formatDate(place.last_activity_at)}
        </p>
        <p className="pl-[23px]">
          {place.approved_observation_count} guide report{place.approved_observation_count === 1 ? "" : "s"} within 500 m
        </p>
      </div>
    );
  }
  return (
    <div className="rounded-[6px] bg-old-soft px-4 py-3.5 text-[13.5px] leading-[1.7] text-old">
      <p className="flex items-center gap-2 font-semibold text-ink">
        <Icon name="clock" size={15} className="text-old" />
        No guide confirmation yet
      </p>
      <p className="pl-[23px]">
        {place.open_question_count
          ? `${place.open_question_count} question${place.open_question_count === 1 ? "" : "s"} waiting for a local check`
          : "Not visited by a guide yet"}
      </p>
    </div>
  );
}

/** A nearby place. No guide photo exists for most places, so the visual is
 * the reference's own imageless "reference" panel -- an honest label of what
 * the place is and whether a guide has been -- rather than a fake picture. */
export function PlaceCard({ place, origin }: { place: PublicLocationSummary; origin?: string }) {
  const type = placeTypeOf(place) ?? "Place";
  const distance = formatMeters(place.distance_meters);
  const description = cleanDescription(place.description);
  const visited = Boolean(place.last_activity_at);

  return (
    <Link href={`/places/${place.location_id}`} className="group flex w-full flex-col overflow-hidden rounded-[8px] border border-border bg-white transition-colors hover:border-border-strong">
      <div className={visited ? "relative bg-[#e9f2ef] px-6 pb-6 pt-7" : "relative bg-[#f0efe8] px-6 pb-6 pt-7"}>
        <Icon name={iconForPlace(place)} size={28} strokeWidth={1.5} className="text-[#5d6f63]" />
        <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6c7a6f]">{type}</p>
        <p className="mt-1.5 text-[22px] font-bold tracking-[-0.02em] text-[#4c5f50]">
          {distance && origin
            ? `${distance} from ${origin}`
            : place.is_area_hub
              ? "Area guide"
              : place.approved_observation_count
                ? `${place.approved_observation_count} report${place.approved_observation_count === 1 ? "" : "s"} nearby`
                : place.open_question_count
                  ? `${place.open_question_count} open question${place.open_question_count === 1 ? "" : "s"}`
                  : (distance ?? type)}
        </p>
        <p className="mt-1 text-[13px] text-[#6c7a6f]">{visited ? "Guide reports nearby" : "Awaiting a guide visit"}</p>
        <Icon name="arrowUpRight" size={16} className="absolute right-4 top-4 text-[#6c7a6f] opacity-0 transition group-hover:opacity-100" />
      </div>
      <div className="flex flex-1 flex-col px-6 pb-6 pt-5">
        <CardEyebrow>
          {themesOf(place)
            .slice(0, 2)
            .map((t) => t.display_name)
            .join(" · ") || type}
        </CardEyebrow>
        <h3 className="mt-2 text-[19px] font-bold leading-[1.4] tracking-[-0.015em] text-ink group-hover:text-accent-deep">{place.name}</h3>
        {description && <p className="mt-2 line-clamp-3 text-[15.5px] leading-[1.75] text-ink-soft">{description}</p>}
        <div className="mt-auto pt-5">
          <CheckPanel place={place} />
          <span className="mt-5 inline-flex items-center gap-2 text-[14.5px] font-bold text-accent-deep">
            <span className="group-hover:underline">Explore this place</span>
            <Icon name="arrowRight" size={15} strokeWidth={2} />
          </span>
        </div>
      </div>
    </Link>
  );
}

/** A single-place group as the reference's wide image-left feature row. */
export function PlaceFeature({ place, eyebrow }: { place: PublicLocationSummary; eyebrow: string }) {
  const description = cleanDescription(place.description);
  return (
    <article className="grid overflow-hidden rounded-[8px] border border-border bg-white md:grid-cols-[1.05fr_1fr]">
      <MapTile center={{ latitude: place.latitude, longitude: place.longitude, label: place.name }} zoom={16} className="relative min-h-[240px] md:min-h-[320px]" />
      <div className="flex flex-col justify-center p-7 sm:p-9">
        <CardEyebrow>{eyebrow}</CardEyebrow>
        <h3 className="mt-2.5 text-[23px] font-bold leading-[1.3] tracking-[-0.02em] text-ink">{place.name}</h3>
        {description && <p className="mt-3 text-[16px] leading-[1.8] text-ink-soft">{description}</p>}
        <div className="mt-6">
          <CheckPanel place={place} />
        </div>
        <div className="mt-6">
          <TextLink href={`/places/${place.location_id}`}>Explore this place</TextLink>
        </div>
      </div>
    </article>
  );
}
