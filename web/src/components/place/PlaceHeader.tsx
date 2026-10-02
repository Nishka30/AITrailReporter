import Image from "next/image";
import Link from "next/link";
import clsx from "clsx";
import type { PublicLocationCategory, PublicLocationSummary, PublicRoute } from "@/lib/content";
import { categoryStateTone, formatDate } from "@/lib/content/freshness";
import { DynamicMap } from "@/components/DynamicMap";
import { TONE_DOT } from "./TrustTag";

function timeOfDay(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Field-guide intro: breadcrumb, what the place is, its name, where it sits
 * on a route, a short lede, its categories (from
 * location_category_assignments), and the latest check -- beside a guide's
 * photo, or a map of the place and its neighbours when no photo exists.
 */
export function PlaceIntro({
  place,
  placeType,
  lede,
  themes,
  notebookAnchor,
  photo,
  nearby,
  route,
  contributingGuides,
  verifiedCount,
}: {
  place: { location_id: string; name: string; latitude: number; longitude: number; last_activity_at: string | null; approved_observation_count: number };
  placeType: string | null;
  lede: string | null;
  themes: PublicLocationCategory[];
  /** When the page has a field notebook, chips jump to its category tab. */
  notebookAnchor: boolean;
  photo: { url: string; caption: string } | null;
  nearby: PublicLocationSummary[];
  route: PublicRoute | null;
  contributingGuides: number;
  verifiedCount: number;
}) {
  const stop = route?.stops.find((s) => s.location_id === place.location_id);

  return (
    <div className="mx-auto max-w-6xl px-5 sm:px-8">
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-1.5 pt-6 text-xs font-medium text-ink-faint">
        <Link href="/explore" className="hover:text-ink">Explore</Link>
        {route && (
          <>
            <span aria-hidden>›</span>
            <span>{route.name}</span>
          </>
        )}
        <span aria-hidden>›</span>
        <span className="text-ink-soft">{place.name}</span>
      </nav>

      <section className="grid gap-10 pb-10 pt-6 md:grid-cols-[1.25fr_1fr] md:items-start md:gap-12">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-ink-faint">
            {placeType ?? "Place"} · A TrailMind place guide
          </p>
          <h1 className="mt-3 font-heading text-4xl font-extrabold tracking-tight text-ink sm:text-5xl">
            {place.name}
            {stop && route && (
              <span className="mt-2 block text-lg font-semibold tracking-normal text-accent-deep sm:text-xl">
                Stop {stop.sequence_order} of {route.stops.length} on {route.name}
              </span>
            )}
          </h1>
          {lede && <p className="mt-4 max-w-[650px] text-base leading-[1.8] text-ink-soft">{lede}</p>}

          {themes.length > 0 && (
            <ul className="mt-5 flex flex-wrap gap-2" aria-label="Categories">
              {themes.map((c) => {
                const chip = (
                  <>
                    <span
                      className={clsx(
                        "h-1.5 w-1.5 rounded-full",
                        c.verified_knowledge.length > 0 ? TONE_DOT[categoryStateTone(c.state)] : "bg-ink-faint/40",
                      )}
                    />
                    {c.display_name}
                  </>
                );
                const className =
                  "inline-flex items-center gap-1.5 rounded-full border border-border bg-paper-elevated px-3 py-1 text-[13px] font-semibold text-ink-soft";
                return (
                  <li key={c.slug}>
                    {notebookAnchor ? (
                      <Link
                        href={`/places/${place.location_id}?category=${c.slug}#notebook`}
                        scroll={false}
                        className={clsx(className, "transition hover:border-border-strong hover:text-ink")}
                      >
                        {chip}
                      </Link>
                    ) : (
                      <span className={className} title={c.verified_knowledge.length > 0 ? "Has guide-verified information" : "Not verified by a guide yet"}>
                        {chip}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          <div className="mt-6 border-l-2 border-accent pl-3 text-xs leading-relaxed text-ink-faint">
            {place.last_activity_at ? (
              <p>
                <span className="font-semibold text-ink-soft">Latest check:</span>{" "}
                {formatDate(place.last_activity_at)}, {timeOfDay(place.last_activity_at)}
              </p>
            ) : (
              <p>
                <span className="font-semibold text-ink-soft">No guide has reported here yet.</span> Anything below is background or
                about nearby places.
              </p>
            )}
            {(contributingGuides > 0 || verifiedCount > 0) && (
              <p>
                {[
                  contributingGuides > 0 && `${contributingGuides} contributing guide${contributingGuides === 1 ? "" : "s"}`,
                  place.approved_observation_count > 0 &&
                    `${place.approved_observation_count} report${place.approved_observation_count === 1 ? "" : "s"}`,
                  verifiedCount > 0 && `${verifiedCount} verified fact${verifiedCount === 1 ? "" : "s"}`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )}
          </div>
        </div>

        {photo ? (
          <figure className="relative hidden h-64 overflow-hidden rounded-xl bg-paper-muted md:block">
            <Image src={photo.url} alt="" fill priority sizes="(min-width: 768px) 40vw, 100vw" className="object-cover" />
            <figcaption className="absolute inset-x-0 bottom-0 flex items-center gap-2 bg-gradient-to-t from-ink/85 to-transparent px-4 pb-3 pt-8 text-xs text-paper">
              {photo.caption}
              <span className="ml-auto text-[10px] text-paper/70">Guide photo</span>
            </figcaption>
          </figure>
        ) : (
          <div className="hidden md:block">
            <DynamicMap
              height={256}
              pins={[
                { id: place.location_id, name: place.name, latitude: place.latitude, longitude: place.longitude, highlight: true },
                ...nearby.map((l) => ({ id: l.location_id, name: l.name, latitude: l.latitude, longitude: l.longitude, href: `/places/${l.location_id}` })),
              ]}
            />
          </div>
        )}
      </section>
    </div>
  );
}

/**
 * Section bar -- links only to sections that actually rendered. Styled as
 * the reference guide's underlined tab row: the first (topmost, currently
 * in view on load) tab reads as active with a teal underline; the rest are
 * plain until clicked/scrolled to. A right-aligned "Ask a guide" action
 * mirrors the reference's own tab-row CTA.
 */
export function OnThisPage({ items, action }: { items: { id: string; label: string }[]; action?: React.ReactNode }) {
  if (items.length < 2) return null;
  return (
    <nav aria-label="On this page" className="border-b border-border bg-paper-elevated">
      <div className="rail mx-auto flex min-h-[54px] max-w-6xl items-stretch gap-7 overflow-x-auto px-5 sm:px-8">
        {items.map((item, i) => (
          <a
            key={item.id}
            href={`#${item.id}`}
            className={clsx(
              "flex shrink-0 items-center border-b-2 text-[15px] font-semibold transition",
              i === 0
                ? "border-accent text-accent-deep"
                : "border-transparent text-ink-soft hover:border-border-strong hover:text-ink",
            )}
          >
            {item.label}
          </a>
        ))}
        {action && <span className="ml-auto flex shrink-0 items-center">{action}</span>}
      </div>
    </nav>
  );
}
