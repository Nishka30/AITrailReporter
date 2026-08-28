import Link from "next/link";
import Image from "next/image";
import type { PublicLocationSummary } from "@/lib/content";
import { timeAgoLabel } from "@/lib/content/freshness";

export function LocationCard({
  location,
  coverPhotoUrl,
  size = "md",
}: {
  location: PublicLocationSummary;
  coverPhotoUrl?: string | null;
  size?: "md" | "lg";
}) {
  return (
    <Link
      href={`/places/${location.location_id}`}
      className="group relative block overflow-hidden rounded-[28px] border border-border/70 bg-paper-elevated shadow-warm transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-1.5 hover:border-transparent hover:shadow-warm-lg"
    >
      <div className={`relative w-full overflow-hidden bg-paper-muted ${size === "lg" ? "aspect-[4/3]" : "aspect-[16/11]"}`}>
        {coverPhotoUrl ? (
          <Image
            src={coverPhotoUrl}
            alt=""
            fill
            sizes="(min-width: 1024px) 33vw, 100vw"
            className="object-cover transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:scale-[1.08]"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-ink-faint">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M3 17l5-6 4 5 3-4 6 7H3Z" />
              <circle cx="8" cy="7" r="2" />
            </svg>
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/45 via-black/5 to-transparent opacity-90" />
        <div className="absolute right-3.5 top-3.5 rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-semibold text-ink shadow-warm backdrop-blur-sm">
          {location.approved_observation_count} report{location.approved_observation_count === 1 ? "" : "s"}
        </div>
      </div>
      <div className="p-5">
        <h3 className="font-heading text-lg font-bold text-ink transition-colors group-hover:text-marigold-deep">{location.name}</h3>
        {location.description && (
          <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-ink-soft">{location.description}</p>
        )}
        <div className="mt-4 flex items-center gap-2 text-xs text-ink-faint">
          <span className="h-1.5 w-1.5 rounded-full bg-ok" />
          <span>{timeAgoLabel(location.last_activity_at)}</span>
        </div>
      </div>
      <div className="pointer-events-none absolute inset-0 rounded-[28px] ring-1 ring-inset ring-white/0 transition group-hover:ring-marigold/25" />
    </Link>
  );
}
