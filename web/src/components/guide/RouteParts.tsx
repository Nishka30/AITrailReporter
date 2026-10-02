import Link from "next/link";
import clsx from "clsx";
import type { KnowledgeState, PublicLocationDetail, PublicObservation, PublicRoute, PublicRouteStop } from "@/lib/content";
import { formatDate } from "@/lib/content/freshness";
import { cleanDescription, placeTypeOf } from "@/lib/content/guide";
import { Avatar, AvatarStack, CardEyebrow } from "./primitives";
import { Icon } from "./Icons";
import { MapTile } from "./MapTile";
import { splitEvidence } from "./ReportCard";

const DOT: Record<KnowledgeState, string> = {
  fresh: "bg-ok-dot",
  aging: "bg-marigold",
  stale: "bg-[#9aa7ae]",
  missing: "border-2 border-[#9aa7ae] bg-white",
};
const STATUS_TEXT: Record<KnowledgeState, string> = {
  fresh: "Recent check",
  aging: "Recheck due",
  stale: "Older check",
  missing: "Not checked yet",
};
const STATUS_COLOR: Record<KnowledgeState, string> = {
  fresh: "text-ok",
  aging: "text-marigold-deep",
  stale: "text-old",
  missing: "text-ink-faint",
};

/** The reference's route strip: every stop on one line, its elevation, and
 * how recently a guide checked it. */
export function RouteStripPanel({ route, guideByStop }: { route: PublicRoute; guideByStop: Record<string, string | undefined> }) {
  const stops = [...route.stops].sort((a, b) => a.sequence_order - b.sequence_order);
  return (
    <div className="rounded-[8px] border border-border bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-soft px-5 py-4">
        <p className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
          <span className="text-[12px] font-bold uppercase tracking-[0.14em] text-ink-soft">The route strip</span>
          <span className="text-[15px] text-ink-soft">Choose a stop to see its field reports.</span>
        </p>
        <a href="#stops" className="inline-flex items-center gap-2 rounded-[5px] border border-[#bfe0ea] bg-accent-soft px-3.5 py-2 text-[14px] text-accent-deep hover:border-accent">
          Whole route <Icon name="arrowRight" size={15} strokeWidth={2} />
        </a>
      </div>
      <ol className="rail flex overflow-x-auto px-2 pb-5 pt-6">
        {stops.map((s, i) => (
          <li key={s.route_stop_id} className="relative min-w-[132px] flex-1">
            {i > 0 && <span aria-hidden className="absolute right-1/2 top-[7px] h-px w-full bg-border-strong" />}
            <Link href={`/places/${s.location_id}`} className="group relative flex flex-col items-center px-2 text-center">
              <span className={clsx("relative z-10 h-3.5 w-3.5 rounded-full ring-4 ring-white", DOT[s.status])} />
              <span className="mt-3 text-[15px] font-bold text-ink group-hover:text-accent-deep">{s.name}</span>
              <span className="mt-0.5 text-[13.5px] text-ink-meta">{s.stop_label ?? (s.elevation_meters != null ? `${s.elevation_meters.toLocaleString()} m` : "")}</span>
              {s.stop_label && s.elevation_meters != null && <span className="text-[13px] text-ink-faint">{s.elevation_meters.toLocaleString()} m</span>}
              <span className={clsx("mt-2.5 text-[13.5px]", STATUS_COLOR[s.status])}>{STATUS_TEXT[s.status]}</span>
              {s.last_observed_at && <span className="text-[13px] text-ink-meta">{formatDate(s.last_observed_at)}</span>}
              {guideByStop[s.location_id] && <span className="text-[13px] text-ink-meta">{guideByStop[s.location_id]}</span>}
            </Link>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-border-soft px-5 py-3 text-[12.5px] text-ink-meta">
        {(["fresh", "aging", "stale"] as KnowledgeState[]).map((k) => (
          <span key={k} className="flex items-center gap-1.5">
            <span className={clsx("h-2 w-2 rounded-full", DOT[k])} />
            {k === "fresh" ? "Recent" : k === "aging" ? "Due" : "Older"}
          </span>
        ))}
        <span>Freshness of the latest guide check at each stop — not a trail-safety rating.</span>
      </div>
    </div>
  );
}

/** Elevation along the route, drawn from the stops' own recorded elevations. */
export function ElevationProfile({ stops }: { stops: PublicRouteStop[] }) {
  const pts = stops.filter((s) => s.elevation_meters != null);
  if (pts.length < 2) return null;
  const W = 640;
  const H = 330;
  const pad = { l: 96, r: 30, t: 34, b: 100 };
  const elevations = pts.map((s) => s.elevation_meters!);
  const min = Math.floor(Math.min(...elevations) / 1000) * 1000;
  const max = Math.ceil(Math.max(...elevations) / 1000) * 1000;
  const x = (i: number) => pad.l + (i * (W - pad.l - pad.r)) / (pts.length - 1);
  const y = (e: number) => pad.t + ((max - e) * (H - pad.t - pad.b)) / (max - min || 1);
  const line = pts.map((s, i) => `${x(i)},${y(s.elevation_meters!)}`).join(" ");
  const ticks: number[] = [];
  for (let e = min; e <= max; e += 1000) ticks.push(e);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Elevation along the route">
      <defs>
        <linearGradient id="elev" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#7c9a6c" stopOpacity="0.32" />
          <stop offset="1" stopColor="#7c9a6c" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="#dfe5e2" strokeDasharray="3 4" />
          <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" fontSize="12" fill="#73808b">
            {t.toLocaleString()}
          </text>
        </g>
      ))}
      <polygon points={`${x(0)},${H - pad.b} ${line} ${x(pts.length - 1)},${H - pad.b}`} fill="url(#elev)" />
      <polyline points={line} fill="none" stroke="#6f8c5f" strokeWidth="2.5" strokeLinejoin="round" />
      {pts.map((s, i) => (
        <g key={s.route_stop_id}>
          <circle cx={x(i)} cy={y(s.elevation_meters!)} r="5" fill="#fff" stroke="#6f8c5f" strokeWidth="2.5" />
          <text x={x(i)} y={y(s.elevation_meters!) - 11} textAnchor="middle" fontSize="12.5" fill="#25384a">
            {s.elevation_meters!.toLocaleString()}
          </text>
          <text x={x(i)} y={H - pad.b + 18} fontSize="12.5" fill="#596875" textAnchor="end" transform={`rotate(-35 ${x(i)} ${H - pad.b + 18})`}>
            {s.name}
          </text>
        </g>
      ))}
    </svg>
  );
}

const PANEL: Record<KnowledgeState, string> = {
  fresh: "bg-[#eef5f1] text-ok",
  aging: "bg-[#fbf4e3] text-marigold-deep",
  stale: "bg-old-soft text-old",
  missing: "bg-old-soft text-old",
};

/** One stop as the reference's stop card: number, elevation, name, what it
 * is, and its latest guide check. */
export function StopCard({ stop, detail, latest }: { stop: PublicRouteStop; detail: PublicLocationDetail | null; latest: PublicObservation | null }) {
  const description = cleanDescription(detail?.description);
  const type = detail ? placeTypeOf(detail) : null;
  return (
    <article className="flex w-full flex-col overflow-hidden rounded-[8px] border border-border bg-white">
      <div className="relative h-[150px]">
        <MapTile center={{ latitude: stop.latitude, longitude: stop.longitude, label: stop.name }} zoom={14} className="absolute inset-0" />
        <span className="absolute bottom-2.5 left-2.5 rounded-[4px] bg-[#263e4c]/85 px-2 py-0.5 text-[11px] text-white">Map</span>
      </div>
      <div className="flex flex-1 flex-col px-[21px] pb-6 pt-5">
        <div className="flex items-baseline justify-between">
          <span className="font-heading text-[26px] font-semibold text-[#9aaab3]">{String(stop.sequence_order).padStart(2, "0")}</span>
          <span className="text-[13.5px] text-ink-meta">{stop.elevation_meters != null ? `${stop.elevation_meters.toLocaleString()} m` : ""}</span>
        </div>
        <Link href={`/places/${stop.location_id}`} className="group mt-3 inline-flex items-center gap-2">
          <h3 className="text-[21px] font-bold tracking-[-0.02em] text-ink group-hover:text-accent-deep">{stop.name}</h3>
          <Icon name="arrowUpRight" size={15} strokeWidth={2} className="text-ink" />
        </Link>
        <p className="mt-1 text-[13.5px] text-ink-meta">{stop.stop_label ?? type ?? "Stop"}</p>
        {description && <p className="mt-3 line-clamp-4 text-[15.5px] leading-[1.75] text-ink-soft">{description}</p>}
        <div className="mt-auto pt-5">
          <div className={clsx("rounded-[6px] px-4 py-3.5 text-[13px] leading-[1.6]", PANEL[stop.status])}>
            {latest ? (
              <>
                <p className="flex gap-2 font-semibold text-ink">
                  <Icon name="clock" size={15} className="mt-0.5 shrink-0" />
                  {splitEvidence(latest.evidence, latest.display_name).title}
                </p>
                <p className="pl-[23px] text-ink-meta">
                  {formatDate(latest.observed_at)} · {latest.guide_name}
                </p>
                <p className="pl-[23px]">{STATUS_TEXT[stop.status]}</p>
              </>
            ) : (
              <p className="flex items-center gap-2 font-semibold text-ink">
                <Icon name="clock" size={15} /> No guide check yet
              </p>
            )}
          </div>
          <Link href={`/places/${stop.location_id}`} className="group mt-5 inline-flex items-center gap-2 text-[14.5px] font-bold text-accent-deep">
            <span className="group-hover:underline">Explore this stop</span>
            <Icon name="arrowRight" size={15} strokeWidth={2} />
          </Link>
        </div>
      </div>
    </article>
  );
}

/** "The week, in perspective": the newest few reports as a numbered digest. */
export function WeekDigest({ title, range, observations }: { title: React.ReactNode; range: string; observations: PublicObservation[] }) {
  const names = [...new Set(observations.map((o) => o.guide_name))];
  return (
    <div className="grid overflow-hidden rounded-[8px] border border-[#d6e6e6] md:grid-cols-[0.75fr_1.25fr]">
      <div className="relative bg-[#e3eeee] p-8 sm:p-9">
        <span className="absolute left-8 top-0 h-[3px] w-14 bg-accent-deep sm:left-9" />
        <p className="eyebrow">The week, in perspective</p>
        <h2 className="mt-3 text-[30px] font-bold leading-[1.18] tracking-[-0.025em] text-ink">{title}</h2>
        <p className="mt-4 text-[14.5px] font-semibold text-ink">{range}</p>
        <p className="mt-3 text-[14.5px] leading-[1.7] text-ink-soft">The details that mattered most, from the latest guide reports.</p>
        <div className="mt-6">
          <AvatarStack names={names.slice(0, 5)} size={30} />
        </div>
        <p className="mt-3 text-[13.5px] leading-[1.6] text-ink-soft">
          Compiled from {observations.length} guide report{observations.length === 1 ? "" : "s"}
          <br />
          by {names.map((n) => n.split(" ")[0]).join(", ")}
        </p>
      </div>
      <ol className="divide-y divide-[#d6e6e6] bg-[#f0f6f6] px-6 sm:px-8">
        {observations.slice(0, 4).map((o, i) => {
          const { title: t, body } = splitEvidence(o.evidence, o.display_name);
          return (
            <li key={o.observation_id}>
              <Link href={`/observations/${o.observation_id}`} className="group flex gap-4 py-6">
                <span className="w-6 shrink-0 pt-0.5 text-[13px] text-ink-faint">{String(i + 1).padStart(2, "0")}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-[17px] font-bold leading-snug tracking-[-0.015em] text-ink group-hover:text-accent-deep">{t}</p>
                  {body && <p className="mt-1.5 line-clamp-2 text-[15.5px] leading-[1.65] text-ink-soft">{body}</p>}
                  <p className="mt-2 text-[14px] text-ink-meta">
                    {formatDate(o.observed_at)} · {o.guide_name}
                    {o.nearest_place_name || o.location_label ? ` · ${o.location_label ?? o.nearest_place_name}` : ""}
                  </p>
                </div>
                <Icon name="arrowUpRight" size={15} strokeWidth={2} className="mt-1 shrink-0 text-ink-meta" />
              </Link>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function GuideCards({ guides }: { guides: { name: string; reports: number; places: string[]; latest: string }[] }) {
  return (
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
      {guides.map((g) => (
        <div key={g.name} className="rounded-[8px] border border-border bg-white p-6">
          <Avatar name={g.name} size={40} />
          <p className="mt-4 text-[17px] font-bold text-ink">{g.name}</p>
          <CardEyebrow className="mt-1.5 normal-case tracking-normal">
            {g.reports} report{g.reports === 1 ? "" : "s"} · latest {formatDate(g.latest)}
          </CardEyebrow>
          <p className="mt-3 text-[14.5px] leading-[1.65] text-ink-soft">{g.places.slice(0, 4).join(" · ")}</p>
        </div>
      ))}
    </div>
  );
}

export function guideStats(observations: PublicObservation[], placeOf: (o: PublicObservation) => string | null) {
  const map = new Map<string, { name: string; reports: number; places: string[]; latest: string }>();
  for (const o of observations) {
    const g = map.get(o.guide_name) ?? { name: o.guide_name, reports: 0, places: [], latest: o.observed_at };
    g.reports += 1;
    const p = placeOf(o);
    if (p && !g.places.includes(p)) g.places.push(p);
    if (o.observed_at > g.latest) g.latest = o.observed_at;
    map.set(o.guide_name, g);
  }
  return [...map.values()].sort((a, b) => b.reports - a.reports);
}
