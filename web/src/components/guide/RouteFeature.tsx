import Link from "next/link";
import clsx from "clsx";
import type { PublicRoute } from "@/lib/content";
import { CardEyebrow, ButtonLink } from "./primitives";
import { MapTile } from "./MapTile";

const STATUS_DOT: Record<string, string> = {
  fresh: "bg-ok-dot",
  aging: "bg-marigold",
  stale: "bg-[#9aa7ae]",
  missing: "border border-[#9aa7ae] bg-white",
};

export function routeCenter(route: PublicRoute) {
  const lats = route.stops.map((s) => s.latitude);
  const lons = route.stops.map((s) => s.longitude);
  return { latitude: (Math.min(...lats) + Math.max(...lats)) / 2, longitude: (Math.min(...lons) + Math.max(...lons)) / 2 };
}

export function routeZoom(route: PublicRoute): number {
  const span = Math.max(
    Math.max(...route.stops.map((s) => s.latitude)) - Math.min(...route.stops.map((s) => s.latitude)),
    Math.max(...route.stops.map((s) => s.longitude)) - Math.min(...route.stops.map((s) => s.longitude)),
  );
  return span > 1 ? 8 : span > 0.4 ? 9 : span > 0.15 ? 10 : span > 0.05 ? 12 : 14;
}

/** Fit factor between tile zoom levels for the route's span. */
export function routeScale(route: PublicRoute): number {
  const lat = Math.max(...route.stops.map((s) => s.latitude)) - Math.min(...route.stops.map((s) => s.latitude));
  return lat > 0.25 && lat <= 0.4 ? 0.72 : 1;
}

export function elevationRange(route: PublicRoute): string | null {
  const e = route.stops.map((s) => s.elevation_meters).filter((m): m is number => m != null);
  if (e.length === 0) return null;
  return `${Math.min(...e).toLocaleString()}–${Math.max(...e).toLocaleString()} m`;
}

/** A route as the reference's wide image-left feature: a real map of the
 * route's stops beside its identity and stop list. */
export function RouteFeature({ route, highlightId }: { route: PublicRoute; highlightId?: string }) {
  const stops = [...route.stops].sort((a, b) => a.sequence_order - b.sequence_order);
  const range = elevationRange(route);
  return (
    <article className="grid overflow-hidden rounded-[8px] border border-border bg-white md:grid-cols-[1fr_1.25fr]">
      <MapTile
        center={{ ...routeCenter(route), label: route.name }}
        pins={stops.map((s) => ({ latitude: s.latitude, longitude: s.longitude, label: s.name }))}
        zoom={routeZoom(route)}
        centerMarker={false}
        line
        scale={routeScale(route)}
        className="relative min-h-[260px]"
      />
      <div className="p-7 sm:p-9">
        <CardEyebrow>
          {stops.length} stop{stops.length === 1 ? "" : "s"}
          {range ? ` · ${range}` : ""}
        </CardEyebrow>
        <h3 className="mt-2.5 text-[25px] font-bold tracking-[-0.025em] text-ink">{route.name}</h3>
        {route.description && <p className="mt-3 text-[16px] leading-[1.8] text-ink-soft">{route.description}</p>}
        <ol className="mt-5 flex flex-wrap gap-x-1 gap-y-2 text-[13.5px]">
          {stops.map((s, i) => (
            <li key={s.route_stop_id} className="flex items-center gap-1">
              {i > 0 && <span className="mx-1 text-ink-faint">→</span>}
              <span className={clsx("h-2 w-2 rounded-full", STATUS_DOT[s.status])} />
              <Link
                href={`/places/${s.location_id}`}
                className={clsx("hover:underline", s.location_id === highlightId ? "font-bold text-ink" : "text-ink-soft")}
              >
                {s.name}
              </Link>
            </li>
          ))}
        </ol>
        <div className="mt-7">
          <ButtonLink href={`/routes/${route.slug}`} variant="primary">
            View the route, stop by stop
          </ButtonLink>
        </div>
      </div>
    </article>
  );
}
