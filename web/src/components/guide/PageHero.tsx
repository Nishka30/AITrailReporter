import Image from "next/image";
import { Breadcrumb } from "./primitives";
import { Icon } from "./Icons";
import { MapTile, MAP_ATTRIBUTION, type MapTilePin } from "./MapTile";

export type HeroVisual =
  | { kind: "photo"; url: string; caption: string; tag: string }
  | { kind: "map"; center: MapTilePin; pins: MapTilePin[]; caption: string; zoom?: number; line?: boolean; scale?: number };

/**
 * The reference guide's page opening: breadcrumb, small uppercase eyebrow,
 * a large name, a teal second line, a lede, and a quiet "latest check" line
 * -- beside one image. A guide photo when one exists, otherwise a real map
 * of the place (always labelled as such).
 */
export function PageHero({
  breadcrumb,
  eyebrow,
  title,
  titleAccent,
  accentOnNewLine = false,
  subtitle,
  lede,
  meta,
  status,
  actions,
  visual,
}: {
  breadcrumb: { label: string; href?: string }[];
  eyebrow: string;
  title: string;
  titleAccent?: string;
  /** Put the teal accent on its own line ("Trekking the / Everest Region"). */
  accentOnNewLine?: boolean;
  subtitle?: string | null;
  lede?: string | null;
  meta?: { icon: Parameters<typeof Icon>[0]["name"]; text: string }[];
  status?: React.ReactNode;
  actions?: React.ReactNode;
  visual: HeroVisual | null;
}) {
  return (
    <section className="page pb-12 pt-7 sm:pb-14">
      {breadcrumb.length > 0 && <Breadcrumb items={breadcrumb} />}
      <div className="mt-3 grid gap-8 lg:grid-cols-[1.35fr_1fr] lg:gap-14">
        <div className="min-w-0">
          <p className="eyebrow flex items-center gap-3">
            {breadcrumb.length === 0 && <span className="h-[2px] w-6 bg-accent" />}
            {eyebrow}
          </p>
          <h1 className="mt-3 text-[40px] font-bold leading-[1.08] tracking-[-0.035em] text-ink sm:text-[50px]">
            {title}
            {titleAccent && accentOnNewLine && <br />}
            {titleAccent && <span className="text-accent">{accentOnNewLine ? "" : " "}{titleAccent}</span>}
          </h1>
          {subtitle && <p className="mt-3 text-[19px] font-bold leading-snug tracking-[-0.02em] text-accent-deep sm:text-[21px]">{subtitle}</p>}
          {lede && <p className="mt-5 max-w-[640px] text-[17px] leading-[1.75] text-ink-soft sm:text-[18px]">{lede}</p>}
          {meta && meta.length > 0 && (
            <ul className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-[15px] text-ink-soft">
              {meta.map((m) => (
                <li key={m.text} className="flex items-center gap-2">
                  <Icon name={m.icon} size={17} className="text-ink-meta" />
                  {m.text}
                </li>
              ))}
            </ul>
          )}
          {status && <div className="mt-5">{status}</div>}
          {actions && <div className="mt-7 flex flex-wrap items-center gap-5">{actions}</div>}
        </div>

        {visual && (
          <figure className="relative h-[240px] overflow-hidden rounded-[8px] bg-paper-muted sm:h-[300px] lg:mt-2">
            {visual.kind === "photo" ? (
              <Image src={visual.url} alt="" fill priority sizes="(min-width: 1024px) 40vw, 100vw" className="object-cover" />
            ) : (
              <MapTile center={visual.center} pins={visual.pins} zoom={visual.zoom ?? 15} line={visual.line} centerMarker={!visual.line} scale={visual.scale} className="absolute inset-0" />
            )}
            <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/45 to-transparent" />
            <figcaption className="absolute inset-x-4 bottom-3 flex items-end justify-between gap-3 text-white">
              <span className="flex items-center gap-1.5 text-[13.5px] font-semibold [text-shadow:0_1px_2px_rgba(0,0,0,.4)]">
                <Icon name="pin" size={15} />
                {visual.caption}
              </span>
              <span className="text-[10.5px] text-white/85 [text-shadow:0_1px_2px_rgba(0,0,0,.4)]">
                {visual.kind === "photo" ? visual.tag : MAP_ATTRIBUTION}
              </span>
            </figcaption>
          </figure>
        )}
      </div>
    </section>
  );
}

export function LatestCheck({ at, detail }: { at: string | null; detail?: string | null }) {
  return (
    <div className="text-[14.5px] leading-[1.7]">
      <p className="flex items-center gap-2.5 text-ink">
        <span className={at ? "h-2 w-2 rounded-full bg-ok-dot" : "h-2 w-2 rounded-full border border-ink-faint"} />
        {at ? (
          <span>
            Latest check: <strong className="font-semibold">{at}</strong>
          </span>
        ) : (
          <span className="text-ink-soft">No guide has reported here yet</span>
        )}
      </p>
      {detail && <p className="pl-[18px] text-ink-meta">{detail}</p>}
    </div>
  );
}
