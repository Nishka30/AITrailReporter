import Image from "next/image";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { content } from "@/lib/content";
import { VoicePlayer } from "@/components/VoicePlayer";
import { formatValueEntries, timeAgoLabel } from "@/lib/content/freshness";
import { stateByAge } from "@/lib/content/locationPage";
import { dateTime } from "@/lib/content/guide";
import { Avatar, Breadcrumb, Note, StatusChip, TextLink, checkChip } from "@/components/guide/primitives";
import { MapTile, MAP_ATTRIBUTION } from "@/components/guide/MapTile";
import { ReportCard, splitEvidence } from "@/components/guide/ReportCard";
import { Icon } from "@/components/guide/Icons";

export async function generateMetadata({ params }: { params: Promise<{ observationId: string }> }): Promise<Metadata> {
  const { observationId } = await params;
  const o = await content.getObservation(observationId);
  if (!o) return {};
  return {
    title: splitEvidence(o.evidence, o.display_name).title,
    description: o.evidence ?? undefined,
  };
}

/**
 * One field report, as its own page: the guide's words beside a photo (or a
 * map of exactly where it was reported), the structured detail, who and
 * when -- then the other recent reports from the same place.
 */
export default async function ObservationPage({ params }: { params: Promise<{ observationId: string }> }) {
  const { observationId } = await params;
  const o = await content.getObservation(observationId);
  if (!o) notFound();

  const label = o.category_display_name ?? o.display_name;
  const chip = checkChip(stateByAge(o.observed_at));
  const { title, body } = splitEvidence(o.evidence, label);
  const details = formatValueEntries(o.value);
  const spot = o.location_label ?? o.nearest_place_name;
  const more = o.nearest_place_id
    ? (await content.listObservations({ locationId: o.nearest_place_id, limit: 7 })).items.filter((x) => x.observation_id !== o.observation_id).slice(0, 3)
    : [];

  return (
    <div className="page pb-20 pt-7">
      <Breadcrumb
        items={[
          { label: "Explore", href: "/explore" },
          ...(o.nearest_place_id ? [{ label: o.nearest_place_name ?? "Place", href: `/places/${o.nearest_place_id}` }] : []),
          { label: "Field report" },
        ]}
      />

      <article className="mt-3 grid gap-10 lg:grid-cols-[1.2fr_1fr] lg:gap-14">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <p className="eyebrow">{label} · Field report</p>
            <StatusChip tone={chip.tone}>{chip.label}</StatusChip>
          </div>
          <h1 className="mt-4 text-[32px] font-bold leading-[1.2] tracking-[-0.03em] text-ink sm:text-[40px]">{o.has_audio && !o.evidence ? "A story from the trail" : title}</h1>
          {body && <p className="mt-4 text-[18px] leading-[1.8] text-ink-soft">{body}</p>}
          {o.safety_critical && (
            <p className="mt-5 flex items-center gap-2 text-[14px] font-semibold text-fix">
              <Icon name="info" size={16} /> Safety-relevant — confirm locally before relying on it.
            </p>
          )}

          <div className="mt-7 flex items-center gap-3.5">
            <Avatar name={o.guide_name} size={44} />
            <div className="leading-tight">
              <p className="text-[16px] font-bold text-ink">{o.guide_name}</p>
              <p className="mt-1 text-[14px] text-ink-meta">Local guide · reviewed before publishing</p>
            </div>
          </div>

          <dl className="mt-7 divide-y divide-border-soft overflow-hidden rounded-[8px] border border-border">
            <div className="grid grid-cols-[150px_1fr] gap-4 px-5 py-3.5 text-[15px]">
              <dt className="text-ink-meta">Visited</dt>
              <dd className="text-ink">
                {dateTime(o.observed_at)} <span className="text-ink-faint">({timeAgoLabel(o.observed_at).toLowerCase()})</span>
              </dd>
            </div>
            {spot && (
              <div className="grid grid-cols-[150px_1fr] gap-4 px-5 py-3.5 text-[15px]">
                <dt className="text-ink-meta">Where</dt>
                <dd className="text-ink">{spot}</dd>
              </div>
            )}
            {details.map((d) => (
              <div key={d.label} className="grid grid-cols-[150px_1fr] gap-4 px-5 py-3.5 text-[15px]">
                <dt className="text-ink-meta">{d.label}</dt>
                <dd className="text-ink">{d.text}</dd>
              </div>
            ))}
            <div className="grid grid-cols-[150px_1fr] gap-4 px-5 py-3.5 text-[15px]">
              <dt className="text-ink-meta">Scope</dt>
              <dd className="text-ink">1 guide · 1 visit · single report</dd>
            </div>
          </dl>

          {o.has_audio && (
            <div className="mt-7">
              <VoicePlayer audioUrl={o.audio_url} transcript={o.transcript} guideName={o.guide_name} />
            </div>
          )}

          <Note className="mt-7">
            One guide&rsquo;s dated report from one visit — a record of what they saw, not a guarantee for your visit. Check the date before relying on it.
          </Note>
        </div>

        <div>
          {o.photo_urls[0] ? (
            <div className="space-y-3">
              {o.photo_urls.slice(0, 3).map((url, i) => (
                <figure key={url} className={`relative overflow-hidden rounded-[8px] bg-paper-muted ${i === 0 ? "h-[340px]" : "h-[200px]"}`}>
                  <Image src={url} alt="" fill sizes="(min-width: 1024px) 40vw, 100vw" className="object-cover" priority={i === 0} />
                  {i === 0 && (
                    <figcaption className="absolute right-3 top-3 rounded-[4px] bg-[#263e4c]/85 px-2 py-0.5 text-[11px] text-white">Guide photo · {dateTime(o.observed_at)}</figcaption>
                  )}
                </figure>
              ))}
            </div>
          ) : o.latitude != null && o.longitude != null ? (
            <figure className="overflow-hidden rounded-[8px] border border-border">
              <MapTile center={{ latitude: o.latitude, longitude: o.longitude, label: spot ?? "Report location" }} zoom={16} className="relative h-[340px]" />
              <figcaption className="flex items-center justify-between gap-3 px-4 py-3 text-[13px] text-ink-meta">
                <span className="flex items-center gap-1.5">
                  <Icon name="pin" size={14} /> Where this was reported
                </span>
                <span className="text-[11.5px] text-ink-faint">{MAP_ATTRIBUTION}</span>
              </figcaption>
            </figure>
          ) : null}
          {o.nearest_place_id && (
            <div className="mt-6">
              <TextLink href={`/places/${o.nearest_place_id}`}>Everything we know about {o.nearest_place_name}</TextLink>
            </div>
          )}
        </div>
      </article>

      {more.length > 0 && (
        <section className="mt-16 border-t border-border pt-12">
          <p className="eyebrow">More from the field notebook</p>
          <h2 className="mt-2.5 text-[29px] font-bold tracking-[-0.025em] text-ink">Other recent reports near {o.nearest_place_name}</h2>
          <div className="mt-8 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {more.map((x) => (
              <div key={x.observation_id} className="flex">
                <ReportCard check={{ observation: x, label: x.category_display_name ?? x.display_name, state: stateByAge(x.observed_at) }} />
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
