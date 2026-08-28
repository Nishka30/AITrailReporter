import Link from "next/link";
import Image from "next/image";
import type { PublicObservation } from "@/lib/content";
import { timeAgoLabel } from "@/lib/content/freshness";

function KindTag({ observation }: { observation: PublicObservation }) {
  if (observation.has_audio) return <span>Voice story</span>;
  if (observation.has_photo) return <span>Photo</span>;
  return <span>Field note</span>;
}

export function ObservationCard({ observation }: { observation: PublicObservation }) {
  return (
    <Link
      href={`/observations/${observation.observation_id}`}
      className="group relative block w-full overflow-hidden rounded-[28px] border border-border/70 bg-paper-elevated shadow-warm transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-1.5 hover:border-transparent hover:shadow-warm-lg"
    >
      {observation.has_photo && observation.photo_url ? (
        <div className="relative aspect-[4/3] w-full overflow-hidden bg-paper-muted">
          <Image
            src={observation.photo_url}
            alt=""
            fill
            sizes="320px"
            className="object-cover transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:scale-[1.08]"
          />
          <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/35 to-transparent" />
          {observation.has_audio && (
            <span className="absolute right-3 top-3 flex h-9 w-9 items-center justify-center rounded-full bg-white/90 text-ink shadow-warm backdrop-blur-sm transition group-hover:bg-marigold">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5v14l11-7z" />
              </svg>
            </span>
          )}
        </div>
      ) : (
        <div className="flex aspect-[4/3] w-full items-center justify-center bg-gradient-to-br from-marigold-soft/70 to-marigold-soft/20 p-6">
          {observation.has_audio ? (
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="text-marigold-deep">
              <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z" />
              <path d="M19 11a7 7 0 0 1-14 0M12 18v3" />
            </svg>
          ) : (
            <p className="font-heading text-lg leading-snug text-ink line-clamp-4">&ldquo;{observation.evidence}&rdquo;</p>
          )}
        </div>
      )}
      <div className="p-5">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-marigold-deep">
          <KindTag observation={observation} />
          <span className="text-ink-faint">·</span>
          <span className="text-ink-faint normal-case">{observation.display_name}</span>
        </div>
        {(observation.has_photo || observation.has_audio) && observation.evidence && (
          <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-ink-soft">{observation.evidence}</p>
        )}
        <div className="mt-3 flex items-center justify-between text-xs text-ink-faint">
          <span>Reported by {observation.guide_name}, local guide</span>
        </div>
        <p className="text-xs text-ink-faint">
          {observation.nearest_place_name ? `Near ${observation.nearest_place_name} · ` : ""}
          {timeAgoLabel(observation.observed_at)}
        </p>
      </div>
      <div className="pointer-events-none absolute inset-0 rounded-[28px] ring-1 ring-inset ring-white/0 transition group-hover:ring-marigold/25" />
    </Link>
  );
}
