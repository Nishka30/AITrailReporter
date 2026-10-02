import Image from "next/image";
import Link from "next/link";
import type { LocalCheck } from "@/lib/content/locationPage";
import { dateTime } from "@/lib/content/guide";
import { Avatar, CardEyebrow, StatusChip, checkChip } from "./primitives";
import { Icon } from "./Icons";

/** First sentence as the headline, the rest as the body -- the guide's own
 * words, never rewritten. */
export function splitEvidence(evidence: string | null, fallback: string): { title: string; body: string | null } {
  const text = (evidence ?? "").trim();
  if (!text) return { title: fallback, body: null };
  const [first, ...rest] = text.match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g) ?? [text];
  const title = first.trim();
  const body = rest.join("").trim();
  return title.length > 110 ? { title: fallback, body: text } : { title, body: body || null };
}

/**
 * One dated guide report as the reference's field-notebook card: photo with
 * the spot it was taken (when there is one), CATEGORY + freshness chip, the
 * guide's own words, who, exactly when, and a link to the full report.
 */
export function ReportCard({ check, showPlace }: { check: LocalCheck; showPlace?: string | null }) {
  const o = check.observation;
  const chip = checkChip(check.state);
  const photo = o.photo_urls[0] ?? null;
  const spot = o.location_label ?? o.nearest_place_name ?? showPlace ?? null;
  const { title, body } = splitEvidence(o.evidence, check.label);

  return (
    <article className="flex w-full flex-col overflow-hidden rounded-[8px] border border-border bg-white">
      {photo && (
        <div className="relative h-[200px] w-full bg-paper-muted">
          <Image src={photo} alt="" fill sizes="(min-width: 1024px) 33vw, 100vw" className="object-cover" />
          <span className="absolute right-3 top-3 rounded-[4px] bg-[#263e4c]/85 px-2 py-0.5 text-[11px] text-white">Guide photo</span>
          {spot && (
            <span className="absolute bottom-3 left-3 flex items-center gap-1.5 rounded-[4px] bg-white px-2.5 py-1 text-[12.5px] font-semibold text-ink">
              <Icon name="pin" size={13} />
              {spot}
            </span>
          )}
        </div>
      )}
      <div className="flex flex-1 flex-col px-[21px] pb-5 pt-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardEyebrow>{check.label}</CardEyebrow>
          <StatusChip tone={chip.tone}>{chip.label}</StatusChip>
        </div>
        <h3 className="mt-3 text-[19px] font-bold leading-[1.45] tracking-[-0.015em] text-ink">{title}</h3>
        {body && <p className="mt-2 line-clamp-4 text-[16px] leading-[1.8] text-ink-soft">{body}</p>}
        {o.safety_critical && check.state !== "superseded" && (
          <p className="mt-3 flex items-center gap-1.5 text-[13px] font-semibold text-fix">
            <Icon name="info" size={14} /> Safety-relevant — confirm locally before relying on it
          </p>
        )}

        <div className="mt-auto pt-5">
          <div className="flex items-center gap-3">
            <Avatar name={o.guide_name} />
            <div className="min-w-0 leading-tight">
              <p className="truncate text-[14px] font-bold text-[#344c5b]">{o.guide_name}</p>
              {!photo && spot && <p className="mt-0.5 truncate text-[13px] text-ink-meta">{spot}</p>}
            </div>
          </div>
          <div className="mt-4 border-t border-border-soft pt-3.5 text-[14px] leading-[1.9] text-ink-meta">
            <p>
              <time dateTime={o.observed_at}>{dateTime(o.observed_at)}</time>
            </p>
            <p>1 guide · 1 visit · single report</p>
          </div>
          <Link
            href={`/observations/${o.observation_id}`}
            className="group mt-3 flex items-center justify-between border-t border-border-soft pt-3.5 text-[14.5px] font-bold text-accent-deep"
          >
            <span className="group-hover:underline">View field report</span>
            <Icon name="arrowUpRight" size={15} strokeWidth={2} />
          </Link>
        </div>
      </div>
    </article>
  );
}
