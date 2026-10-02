import Link from "next/link";
import clsx from "clsx";
import type { PublicRoute, PublicRouteStop } from "@/lib/content";
import { checkLabel, formatDate, freshnessTone } from "@/lib/content/freshness";
import { TONE_DOT } from "@/components/place/TrustTag";

/** Only render a strip when there is a real ORDERED route to show -- a
 * single resolved stop is a place, not a route. */
export const MIN_ROUTE_STRIP_STOPS = 2;

export function hasRouteStrip(route: PublicRoute | null): route is PublicRoute {
  return Boolean(route && route.stops.length >= MIN_ROUTE_STRIP_STOPS);
}

/**
 * A route's stops in order, joined by a line: number, name, elevation, and
 * when a guide last reported there. Takes the route as plain data -- nothing
 * Everest-specific -- so the same component serves any seeded route. The
 * current stop is highlighted, every other stop links to its own page.
 */
function Stop({ stop, isCurrent, isLast }: { stop: PublicRouteStop; isCurrent: boolean; isLast: boolean }) {
  const tone = freshnessTone(stop.status);
  const body = (
    <div
      className={clsx(
        "relative h-full rounded-3xl border p-4 transition-all duration-300",
        isCurrent
          ? "border-transparent bg-ink text-paper shadow-warm"
          : "border-border bg-paper-elevated hover:-translate-y-0.5 hover:border-border-strong hover:shadow-warm",
      )}
    >
      <p className={clsx("font-heading text-xs font-extrabold", isCurrent ? "text-accent-soft" : "text-accent-deep")}>
        {String(stop.sequence_order).padStart(2, "0")}
      </p>
      <p className={clsx("mt-1 text-[15px] font-semibold leading-snug", isCurrent ? "text-paper" : "text-ink")}>
        {stop.stop_label ?? stop.name}
      </p>
      {stop.elevation_meters != null && (
        <p className={clsx("mt-0.5 text-xs", isCurrent ? "text-paper/65" : "text-ink-faint")}>
          {stop.elevation_meters.toLocaleString()} m
        </p>
      )}
      <div className="mt-3 flex items-center gap-1.5">
        <span className={clsx("h-1.5 w-1.5 rounded-full", TONE_DOT[tone])} />
        <span className={clsx("text-xs font-semibold", isCurrent ? "text-paper/85" : "text-ink-soft")}>{checkLabel(stop.status)}</span>
      </div>
      {stop.last_observed_at && (
        <p className={clsx("mt-0.5 text-[11px]", isCurrent ? "text-paper/55" : "text-ink-faint")}>
          {formatDate(stop.last_observed_at)}
        </p>
      )}
    </div>
  );

  return (
    <li className="relative flex w-[168px] shrink-0 flex-col">
      {!isLast && <span aria-hidden className="absolute left-[calc(100%-4px)] top-8 h-px w-[20px] bg-border-strong" />}
      {isCurrent ? (
        <div aria-current="location" className="h-full">{body}</div>
      ) : (
        <Link href={`/places/${stop.location_id}`} className="block h-full">
          {body}
        </Link>
      )}
    </li>
  );
}

export function RouteStrip({ route, currentLocationId }: { route: PublicRoute; currentLocationId: string }) {
  return (
    <div>
      <ol className="rail -mx-5 flex gap-3 overflow-x-auto px-5 pb-2 sm:mx-0 sm:px-0">
        {route.stops.map((stop, i) => (
          <Stop
            key={stop.route_stop_id}
            stop={stop}
            isCurrent={stop.location_id === currentLocationId}
            isLast={i === route.stops.length - 1}
          />
        ))}
      </ol>
      <p className="mt-3 text-xs text-ink-faint">
        Shows when a guide last reported at each stop — not a safety rating, and not a walking-time estimate.
      </p>
    </div>
  );
}
