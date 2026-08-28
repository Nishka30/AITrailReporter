import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { content } from "@/lib/content";
import { ConditionBadge } from "@/components/ConditionBadge";
import { SafetyBanner } from "@/components/SafetyBanner";
import { PhotoGrid } from "@/components/PhotoGrid";
import { VoicePlayer } from "@/components/VoicePlayer";
import { ObservationCard } from "@/components/ObservationCard";
import { EmptyState } from "@/components/EmptyState";
import { DynamicMap } from "@/components/DynamicMap";
import { AskAboutPlace } from "@/components/AskAboutPlace";
import { Reveal, RevealGroup, RevealItem } from "@/components/motion/Reveal";
import { timeAgoLabel } from "@/lib/content/freshness";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locationId: string }>;
}): Promise<Metadata> {
  const { locationId } = await params;
  const place = await content.getLocation(locationId);
  if (!place) return {};
  return {
    title: place.name,
    description: place.description ?? `Recent conditions and traveller reports for ${place.name}.`,
  };
}

export default async function PlacePage({
  params,
}: {
  params: Promise<{ locationId: string }>;
}) {
  const { locationId } = await params;
  const [place, allLocations] = await Promise.all([content.getLocation(locationId), content.listLocations(50)]);
  if (!place) notFound();

  const heroPhoto = place.recent_observations.find((o) => o.photo_url)?.photo_url ?? null;
  const voiceStory = place.recent_observations.find((o) => o.has_audio) ?? null;
  const nearby = allLocations.filter((l) => l.location_id !== place.location_id).slice(0, 8);

  return (
    <div>
      {/* Hero */}
      <section className="grain relative flex min-h-[70vh] items-end overflow-hidden bg-ink">
        {heroPhoto ? (
          <Image src={heroPhoto} alt="" fill priority sizes="100vw" className="object-cover opacity-[0.7]" />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-br from-ink via-ink-soft to-marigold-deep/40" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-ink via-ink/35 to-ink/5" />
        <div className="relative mx-auto w-full max-w-5xl px-5 pb-14 pt-28 sm:px-8">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-marigold-soft">Place</p>
          <h1 className="mt-3 font-heading text-5xl font-extrabold tracking-tight text-paper sm:text-6xl">{place.name}</h1>
          {place.description && <p className="mt-4 max-w-2xl text-lg leading-relaxed text-paper/80">{place.description}</p>}
          <div className="mt-6 flex items-center gap-2 text-sm text-paper/65">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" />
            {timeAgoLabel(place.last_activity_at)} · {place.approved_observation_count} report
            {place.approved_observation_count === 1 ? "" : "s"}
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-5xl px-5 py-16 sm:px-8">
        <Reveal>
          <AskAboutPlace placeName={place.name} conditions={place.conditions} observations={place.recent_observations} />
        </Reveal>
        <SafetyBanner conditions={place.conditions} observations={place.recent_observations} />

        {/* Right Now */}
        <Reveal>
          <section className="mt-14">
            <h2 className="font-heading text-3xl font-extrabold tracking-tight text-ink">Right now</h2>
            <p className="mt-1.5 text-sm text-ink-soft">What we actually know about this place, and how current it is.</p>
            <div className="rail -mx-5 mt-6 flex gap-3 overflow-x-auto px-5 pb-2 sm:mx-0 sm:flex-wrap sm:px-0">
              {place.conditions.map((c) => (
                <ConditionBadge key={c.knowledge_type} condition={c} />
              ))}
            </div>
          </section>
        </Reveal>

        {/* Photos */}
        {place.photo_count > 0 && (
          <Reveal>
            <section className="mt-20">
              <div className="mb-6 flex items-end justify-between">
                <h2 className="font-heading text-3xl font-extrabold tracking-tight text-ink">Photos</h2>
                {place.photo_count > 4 && (
                  <Link href={`/places/${place.location_id}/photos`} className="text-sm font-semibold text-marigold-deep hover:underline">
                    See all {place.photo_count} →
                  </Link>
                )}
              </div>
              <PhotoGrid observations={place.recent_observations.slice(0, 8)} />
            </section>
          </Reveal>
        )}

        {/* Voice story */}
        {voiceStory && (
          <Reveal>
            <section className="mt-20">
              <h2 className="font-heading text-3xl font-extrabold tracking-tight text-ink">A voice from the trail</h2>
              <div className="mt-6">
                <VoicePlayer audioUrl={voiceStory.audio_url} transcript={voiceStory.transcript} guideName={voiceStory.guide_name} />
              </div>
            </section>
          </Reveal>
        )}

        {/* Field notes */}
        <Reveal>
          <section className="mt-20">
            <h2 className="font-heading text-3xl font-extrabold tracking-tight text-ink">What people have noticed</h2>
            {place.recent_observations.length === 0 ? (
              <div className="mt-6">
                <EmptyState title="No reports yet" body="Be the first — reports come in from local guides in the field." />
              </div>
            ) : (
              <RevealGroup className="mt-6 grid gap-6 sm:grid-cols-2">
                {place.recent_observations.slice(0, 6).map((o) => (
                  <RevealItem key={o.observation_id}>
                    <ObservationCard observation={o} />
                  </RevealItem>
                ))}
              </RevealGroup>
            )}
            {place.recent_observations.length > 6 && (
              <Link
                href={`/places/${place.location_id}/stories`}
                className="mt-6 inline-block text-sm font-semibold text-marigold-deep hover:underline"
              >
                See every report →
              </Link>
            )}
          </section>
        </Reveal>

        {/* Nearby */}
        {nearby.length > 0 && (
          <Reveal>
            <section className="mt-20">
              <h2 className="font-heading text-3xl font-extrabold tracking-tight text-ink">Nearby places</h2>
              <div className="mt-6 grid gap-8 md:grid-cols-[1.1fr_1fr]">
                <DynamicMap
                  pins={[
                    { id: place.location_id, name: place.name, latitude: place.latitude, longitude: place.longitude, highlight: true },
                    ...nearby.map((l) => ({ id: l.location_id, name: l.name, latitude: l.latitude, longitude: l.longitude, href: `/places/${l.location_id}` })),
                  ]}
                />
                <ul className="space-y-1">
                  {nearby.map((l) => (
                    <li key={l.location_id}>
                      <Link
                        href={`/places/${l.location_id}`}
                        className="flex items-center justify-between rounded-2xl px-4 py-3 text-sm transition hover:bg-paper-muted"
                      >
                        <span className="font-medium text-ink">{l.name}</span>
                        <span className="text-ink-faint">{timeAgoLabel(l.last_activity_at)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          </Reveal>
        )}
      </div>
    </div>
  );
}
