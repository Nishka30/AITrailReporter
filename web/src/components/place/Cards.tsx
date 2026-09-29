import Image from "next/image";
import Link from "next/link";
import type { PublicLocationSummary } from "@/lib/content";
import type { LocalCheck } from "@/lib/content/locationPage";
import { placeTypeOf } from "@/lib/content/locationPage";
import { checkLabel, formatDate, formatDistance, formatValueEntries, freshnessTone } from "@/lib/content/freshness";
import { StatePill } from "./TrustTag";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
}

function timeOfDay(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

/** A short headline for a report: its structured value ("Trail Condition:
 * Muddy, Paved") when it has one, else the first sentence of the guide's
 * own words. Never invented text. */
function reportTitle(check: LocalCheck): string {
  const entries = formatValueEntries(check.observation.value).filter((e) => e.label !== "Answer Text");
  if (entries.length > 0) return entries.slice(0, 2).map((e) => e.text).join(", ");
  const evidence = check.observation.evidence ?? "";
  const firstSentence = evidence.split(/(?<=[.!?])\s/)[0] ?? "";
  return firstSentence.length > 90 ? `${firstSentence.slice(0, 87)}…` : firstSentence || check.label;
}

/**
 * One approved guide report, as a field-notebook card: optional photo with
 * the spot it was taken, CATEGORY · freshness, a headline, the guide's own
 * words, who and exactly when. An older report of the same kind reads
 * "Older report" -- never as current.
 */
export function ReportCard({ check }: { check: LocalCheck }) {
  const o = check.observation;
  const tone = check.state === "superseded" ? "neutral" : freshnessTone(check.state);
  const photo = o.photo_urls[0] ?? null;
  const spot = o.location_label ?? o.nearest_place_name;
  const title = reportTitle(check);
  const body = o.evidence && o.evidence !== title ? o.evidence : null;

  return (
    <article className="flex w-full flex-col overflow-hidden rounded-xl border border-border bg-paper-elevated transition hover:shadow-warm">
      {photo && (
        <div className="relative h-48 w-full overflow-hidden bg-paper-muted">
          <Image src={photo} alt="" fill sizes="(min-width: 1024px) 33vw, 100vw" className="object-cover" />
          {spot && (
            <span className="absolute bottom-3 left-3 rounded-md bg-paper-elevated/95 px-2 py-1 text-[11px] font-bold text-ink shadow-warm">
              {spot}
            </span>
          )}
        </div>
      )}
      <div className="flex flex-1 flex-col p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-ink-faint">{check.label}</span>
          <StatePill tone={tone}>{check.state === "superseded" ? "Older report" : checkLabel(check.state)}</StatePill>
        </div>
        <h3 className="mt-3 font-heading text-[17px] font-bold leading-snug text-ink">{title}</h3>
        {body && <p className="mt-2 line-clamp-4 text-sm leading-[1.75] text-ink-soft">{body}</p>}
        {o.safety_critical && <p className="mt-2 text-xs font-semibold text-fix">Safety-relevant report</p>}

        <div className="mt-auto pt-5">
          <div className="flex items-center gap-2.5 border-t border-border pt-4">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink text-[10px] font-bold text-marigold-soft">
              {initials(o.guide_name)}
            </span>
            <div className="min-w-0 flex-1 text-xs leading-tight">
              <p className="truncate font-semibold text-ink">{o.guide_name}</p>
              <p className="text-ink-faint">
                <time dateTime={o.observed_at}>
                  {formatDate(o.observed_at)} · {timeOfDay(o.observed_at)}
                </time>
              </p>
            </div>
            <Link href={`/observations/${o.observation_id}`} className="shrink-0 text-xs font-semibold text-marigold-deep hover:underline">
              View report →
            </Link>
          </div>
        </div>
      </div>
    </article>
  );
}

/**
 * A nearby place in "Get your bearings": what it is (its DB place_type),
 * how far, and when a guide last reported there -- or that nobody has.
 */
export function PlaceCard({ place }: { place: PublicLocationSummary }) {
  const placeType = placeTypeOf(place);
  const distance = formatDistance(place.distance_meters);
  const themes = (place.categories ?? []).filter((c) => c.kind === "theme").slice(0, 3);

  return (
    <Link
      href={`/places/${place.location_id}`}
      className="group flex w-full flex-col rounded-xl border border-border bg-paper-elevated p-5 transition hover:border-border-strong hover:shadow-warm"
    >
      <div className="flex items-center justify-between gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-ink-faint">
        <span>{placeType ?? "Place"}</span>
        {distance && <span className="normal-case tracking-normal">{distance} away</span>}
      </div>
      <h3 className="mt-2 font-heading text-[17px] font-bold leading-snug text-ink group-hover:text-marigold-deep">{place.name}</h3>
      {place.description && <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-ink-soft">{place.description}</p>}
      {themes.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {themes.map((c) => (
            <li key={c.slug} className="rounded-full bg-paper-muted px-2.5 py-0.5 text-[11px] font-medium text-ink-soft">
              {c.display_name}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-auto flex items-center justify-between gap-2 pt-4 text-xs">
        <span className="flex items-center gap-1.5 text-ink-faint">
          <span className={place.last_activity_at ? "h-1.5 w-1.5 rounded-full bg-ok" : "h-1.5 w-1.5 rounded-full bg-ink-faint/50"} />
          {place.last_activity_at ? `Last report ${formatDate(place.last_activity_at)}` : "Not checked by a guide yet"}
        </span>
        <span className="font-semibold text-marigold-deep">Explore →</span>
      </div>
    </Link>
  );
}
