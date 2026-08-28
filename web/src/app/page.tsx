import Image from "next/image";
import Link from "next/link";
import { content } from "@/lib/content";
import { coverPhotoFor } from "@/lib/content/coverPhoto";
import { AskAnything } from "@/components/AskAnything";
import { LocationCard } from "@/components/LocationCard";
import { ObservationCard } from "@/components/ObservationCard";
import { GeolocationNear } from "@/components/GeolocationNear";
import { EmptyState } from "@/components/EmptyState";
import { LiveTicker } from "@/components/LiveTicker";
import { Reveal, RevealGroup, RevealItem } from "@/components/motion/Reveal";
import { CursorGlow } from "@/components/motion/CursorGlow";
import { CountUp } from "@/components/motion/CountUp";
import { timeAgoLabel } from "@/lib/content/freshness";

export default async function HomePage() {
  const [locations, recent] = await Promise.all([
    content.listLocations(12),
    content.listObservations({ limit: 24 }),
  ]);

  const featured = locations.slice(0, 6);
  const featuredWithPhotos = await Promise.all(
    featured.map(async (l) => ({ location: l, photo: await coverPhotoFor(l.location_id) })),
  );
  const heroPhoto = featuredWithPhotos.find((f) => f.photo)?.photo ?? null;
  const heroPlace = featuredWithPhotos.find((f) => f.photo)?.location ?? featured[0] ?? null;

  const stories = recent.items.filter((o) => o.has_photo || o.has_audio);
  const notes = recent.items.filter((o) => !o.has_photo && !o.has_audio).slice(0, 4);

  const totalReports = locations.reduce((sum, l) => sum + l.approved_observation_count, 0);

  return (
    <div>
      {/* Hero */}
      <section className="grain relative flex min-h-[94vh] flex-col overflow-hidden bg-ink">
        {heroPhoto ? (
          <Image src={heroPhoto} alt="" fill priority sizes="100vw" className="object-cover opacity-[0.55]" />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-br from-ink via-ink-soft to-marigold-deep/40" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-ink via-ink/50 to-ink/20" />
        <div className="absolute inset-0 bg-gradient-to-r from-ink/70 via-ink/10 to-transparent" />
        <CursorGlow />

        <div className="relative flex flex-1 items-center">
          <div className="mx-auto w-full max-w-5xl px-5 py-28 sm:px-8">
            <Reveal>
              <p className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.22em] text-marigold-soft">
                <span className="h-1.5 w-1.5 rounded-full bg-marigold" />
                Real reports, checked by real people
              </p>
            </Reveal>
            <Reveal delay={0.08}>
              <h1 className="mt-5 font-heading text-[13vw] font-extrabold leading-[0.98] tracking-[-0.03em] text-paper sm:text-6xl lg:text-[5.5rem]">
                See what a place
                <br />
                is really like.
              </h1>
            </Reveal>
            <Reveal delay={0.16}>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-paper/80">
                Not what a place should be like — what it&rsquo;s like right now, from people who
                were actually there. Ask it anything.
              </p>
            </Reveal>
            <Reveal delay={0.24}>
              <div className="mt-9 max-w-2xl">
                <AskAnything locations={locations} />
              </div>
            </Reveal>
            {heroPlace && (
              <Reveal delay={0.32}>
                <p className="mt-6 text-sm text-paper/65">
                  Currently trending:{" "}
                  <Link href={`/places/${heroPlace.location_id}`} className="font-semibold text-marigold-soft underline-offset-4 hover:underline">
                    {heroPlace.name}
                  </Link>
                </p>
              </Reveal>
            )}
          </div>
        </div>

        <div className="relative">
          <LiveTicker observations={recent.items} />
        </div>
      </section>

      <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
        {/* Near you */}
        <Reveal className="mb-24">
          <GeolocationNear locations={locations} />
        </Reveal>

        {/* Recently updated places */}
        <section className="mb-28">
          <Reveal>
            <div className="mb-9 flex items-end justify-between gap-4">
              <div>
                <h2 className="font-heading text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">Recently updated places</h2>
                <p className="mt-2 text-sm text-ink-soft">
                  <CountUp value={totalReports} className="font-semibold text-ink" /> field report
                  {totalReports === 1 ? "" : "s"} across {locations.length} places, moderated before they publish.
                </p>
              </div>
              <Link
                href="/explore"
                className="hidden shrink-0 items-center gap-1.5 rounded-full border border-border px-4 py-2 text-sm font-semibold text-ink transition hover:border-ink sm:flex"
              >
                Explore all <span aria-hidden>→</span>
              </Link>
            </div>
          </Reveal>
          {featuredWithPhotos.length === 0 ? (
            <EmptyState title="No approved places yet" body="Once the moderation team approves a report, it will appear here." />
          ) : (
            <RevealGroup className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {featuredWithPhotos.map(({ location, photo }) => (
                <RevealItem key={location.location_id}>
                  <LocationCard location={location} coverPhotoUrl={photo} size="lg" />
                </RevealItem>
              ))}
            </RevealGroup>
          )}
          <Link href="/explore" className="mt-8 block text-center text-sm font-semibold text-marigold-deep hover:underline sm:hidden">
            Explore all places →
          </Link>
        </section>

        {/* Traveller stories */}
        {stories.length > 0 && (
          <section className="mb-28">
            <Reveal>
              <div className="mb-9">
                <h2 className="font-heading text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">People who were here recently</h2>
                <p className="mt-2 text-sm text-ink-soft">Photos and voice stories from the last few days on the ground.</p>
              </div>
            </Reveal>
            <div className="rail -mx-5 flex gap-5 overflow-x-auto px-5 pb-4 sm:-mx-8 sm:px-8">
              {stories.map((o) => (
                <div key={o.observation_id} className="w-72 shrink-0 sm:w-80">
                  <ObservationCard observation={o} />
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Field notes strip */}
        {notes.length > 0 && (
          <section className="mb-28">
            <Reveal>
              <h2 className="font-heading text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">What travellers are noticing</h2>
            </Reveal>
            <RevealGroup className="mt-9 grid gap-4 sm:grid-cols-2">
              {notes.map((o) => (
                <RevealItem key={o.observation_id}>
                  <Link
                    href={`/observations/${o.observation_id}`}
                    className="group block h-full rounded-[24px] border border-border/70 bg-paper-elevated p-6 shadow-warm transition-all duration-300 hover:-translate-y-1 hover:shadow-warm-lg"
                  >
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-marigold-deep">{o.display_name}</p>
                    <p className="mt-2.5 text-[16px] leading-relaxed text-ink">&ldquo;{o.evidence}&rdquo;</p>
                    <p className="mt-4 text-xs text-ink-faint">
                      {o.guide_name} · {timeAgoLabel(o.observed_at)}
                    </p>
                  </Link>
                </RevealItem>
              ))}
            </RevealGroup>
          </section>
        )}

        {/* How it works */}
        <Reveal>
          <section className="grain relative overflow-hidden rounded-[32px] border border-border bg-ink p-8 sm:p-14">
            <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-marigold/20 blur-3xl" />
            <h2 className="relative font-heading text-3xl font-extrabold tracking-tight text-paper sm:text-4xl">
              Not a guidebook.
              <br />A living record.
            </h2>
            <div className="relative mt-10 grid gap-10 sm:grid-cols-3">
              <div>
                <p className="font-heading text-3xl font-extrabold text-marigold">01</p>
                <p className="mt-3 font-semibold text-paper">Someone on the ground reports it</p>
                <p className="mt-2 text-sm leading-relaxed text-paper/60">
                  A local guide or traveller notes a condition, snaps a photo, or records a quick voice update.
                </p>
              </div>
              <div>
                <p className="font-heading text-3xl font-extrabold text-marigold">02</p>
                <p className="mt-3 font-semibold text-paper">A person checks it</p>
                <p className="mt-2 text-sm leading-relaxed text-paper/60">
                  Every report is reviewed by a moderator before it ever reaches this site — nothing publishes
                  automatically.
                </p>
              </div>
              <div>
                <p className="font-heading text-3xl font-extrabold text-marigold">03</p>
                <p className="mt-3 font-semibold text-paper">It ages, honestly</p>
                <p className="mt-2 text-sm leading-relaxed text-paper/60">
                  We track how old each report is. When it gets old, we say so — and quietly ask the next
                  person on the trail to check again.
                </p>
              </div>
            </div>
          </section>
        </Reveal>
      </div>
    </div>
  );
}
