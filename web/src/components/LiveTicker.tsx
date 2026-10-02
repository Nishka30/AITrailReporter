import type { PublicObservation } from "@/lib/content";
import { timeAgoLabel } from "@/lib/content/freshness";

function Item({ o }: { o: PublicObservation }) {
  return (
    <span className="flex shrink-0 items-center gap-2 px-6 text-sm text-ink-soft">
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-ok" />
      <span className="font-medium text-ink">{o.display_name}</span>
      {o.nearest_place_name && <span>near {o.nearest_place_name}</span>}
      <span className="text-ink-faint">· {timeAgoLabel(o.observed_at)}</span>
    </span>
  );
}

/** A slow, seamless, infinitely-looping strip of real recent reports --
 * reinforces "this is a living record" viscerally rather than just saying
 * it. Pure CSS animation (see .marquee-track in globals.css); the content
 * is duplicated so the loop point is invisible. */
export function LiveTicker({ observations }: { observations: PublicObservation[] }) {
  if (observations.length === 0) return null;
  return (
    <div className="relative overflow-hidden border-t border-border bg-paper-muted py-3">
      <div className="marquee-track flex w-max">
        {[...observations, ...observations].map((o, i) => (
          <Item key={`${o.observation_id}-${i}`} o={o} />
        ))}
      </div>
      <div className="pointer-events-none absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-paper-muted to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-paper-muted to-transparent" />
    </div>
  );
}
