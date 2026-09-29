import Link from "next/link";
import clsx from "clsx";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { content } from "@/lib/content";
import { SafetyBanner } from "@/components/SafetyBanner";
import { PhotoGrid } from "@/components/PhotoGrid";
import { VoicePlayer } from "@/components/VoicePlayer";
import { AskAboutPlace } from "@/components/AskAboutPlace";
import { ResearchSummarySection, hasReferenceContent, type LedeField } from "@/components/ResearchSummarySection";
import { PopularQuestionsSection } from "@/components/PopularQuestionsSection";
import { RouteStrip, hasRouteStrip } from "@/components/RouteStrip";
import { OnThisPage, PlaceIntro } from "@/components/place/PlaceHeader";
import { VerifiedKnowledge } from "@/components/place/CurrentChecks";
import { SourcesAndContributors } from "@/components/place/AreaSections";
import { CategoryTabs } from "@/components/place/CategoryTabs";
import { PlaceCard, ReportCard } from "@/components/place/Cards";
import { PlaceSectionHeading } from "@/components/place/TrustTag";
import { formatDate } from "@/lib/content/freshness";
import {
  buildLocalChecks,
  placeTabs,
  primaryPlaceType,
  reportTabKeys,
  reportTabs,
  themeCategories,
  themeKeysOf,
  unreportedConditionNames,
  verifiedCategories,
} from "@/lib/content/locationPage";

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
    description:
      place.description ?? place.research_summary?.known_for ?? `Recent guide reports and background for ${place.name}.`,
  };
}

function Section({
  id,
  band = false,
  children,
}: {
  id: string;
  band?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className={clsx("scroll-mt-20 py-14", band && "border-y border-border bg-paper-muted/50")}>
      <div className="mx-auto max-w-6xl px-5 sm:px-8">{children}</div>
    </section>
  );
}

/**
 * Location page as a field guide (structure taken from the reference
 * Everest guide pages, colours/typography our own):
 *   intro (identity, categories, latest check) -> section bar ->
 *   place reference (web research) -> field notebook (dated guide reports,
 *   tabbed by category) -> verified key facts -> answers -> route ->
 *   get your bearings (nearby places, tabbed by their categories) ->
 *   guides' photos/voice -> sources.
 * Every section renders only with real data; each names its trust layer.
 */
export default async function PlacePage({
  params,
  searchParams,
}: {
  params: Promise<{ locationId: string }>;
  searchParams: Promise<{ category?: string }>;
}) {
  const [{ locationId }, sp] = await Promise.all([params, searchParams]);
  const place = await content.getLocation(locationId);
  if (!place) notFound();

  const research = place.research_summary?.status === "completed" ? place.research_summary : null;
  const themes = themeCategories(place.categories);
  const verified = verifiedCategories(place.categories);
  const verifiedFactCount = verified.reduce((n, c) => n + c.verified_knowledge.length, 0);
  const checks = buildLocalChecks(place.recent_observations, place.conditions, place.categories);
  const unreported = unreportedConditionNames(place.conditions);
  const guideNames = [...new Set(place.recent_observations.map((o) => o.guide_name))];

  // One short lede in the intro; the reference section then skips that field.
  const [lede, ledeField]: [string | null, LedeField] = place.description
    ? [place.description, null]
    : research?.description
      ? [research.description, "description"]
      : research?.known_for
        ? [research.known_for, "known_for"]
        : [null, null];

  const photoObservation = place.recent_observations.find((o) => o.photo_urls[0]);
  const introPhoto = photoObservation
    ? {
        url: photoObservation.photo_urls[0]!,
        caption: `${photoObservation.location_label ?? place.name} · ${formatDate(photoObservation.observed_at)}`,
      }
    : null;
  const voiceStory = place.recent_observations.find((o) => o.has_audio) ?? null;
  const bearingTabs = placeTabs(place.nearby);

  const show = {
    reference: hasReferenceContent(research, ledeField),
    notebook: checks.length > 0,
    verified: verified.length > 0,
    answers: place.popular_questions.length > 0,
    route: hasRouteStrip(place.route),
    bearings: place.nearby.length > 0,
    media: place.photo_count > 0 || voiceStory !== null,
    sources: guideNames.length > 0 || (research?.source_urls.length ?? 0) > 0,
  };

  const toc = [
    show.reference && { id: "about", label: "About" },
    show.notebook && { id: "notebook", label: "Latest checks" },
    show.verified && { id: "verified", label: "Verified facts" },
    show.answers && { id: "answers", label: "Current answers" },
    show.route && { id: "route", label: "Route" },
    show.bearings && { id: "bearings", label: "Explore nearby" },
    show.media && { id: "photos", label: "Photos" },
    show.sources && { id: "sources", label: "Sources" },
  ].filter(Boolean) as { id: string; label: string }[];

  const emptyCategoryMessages = Object.fromEntries(
    themes.map((t) => [
      t.slug,
      t.verified_knowledge.length > 0
        ? `No recent guide report about ${t.display_name.toLowerCase()} here — see the verified facts below.`
        : `Not checked yet: no guide has reported on ${t.display_name.toLowerCase()} here.`,
    ]),
  );

  return (
    <div>
      <PlaceIntro
        place={place}
        placeType={primaryPlaceType(place.categories)}
        lede={lede}
        themes={themes}
        notebookAnchor={show.notebook}
        photo={introPhoto}
        nearby={place.nearby}
        route={show.route ? place.route : null}
        contributingGuides={guideNames.length}
        verifiedCount={verifiedFactCount}
      />
      <OnThisPage items={toc} />

      <div className="mx-auto max-w-6xl px-5 sm:px-8">
        <SafetyBanner conditions={place.conditions} observations={place.recent_observations} />
      </div>

      {show.reference && research && (
        <Section id="about" band>
          <PlaceSectionHeading
            kind="research"
            eyebrow="Place reference · background research"
            title={`About ${place.name}`}
            intro="Planning background gathered from public sources. It describes the place in general — for how things are right now, see the guide checks."
          />
          <ResearchSummarySection summary={research} lede={ledeField} />
        </Section>
      )}

      {show.notebook && (
        <Section id="notebook">
          <PlaceSectionHeading
            kind="live"
            eyebrow="The local field notebook"
            title={`The latest around ${place.name}`}
            intro="Dated reports from local guides' visits, newest first. Filter by category."
            aside={
              place.recent_observations.length > 6 && (
                <Link href={`/places/${place.location_id}/stories`} className="text-sm font-semibold text-marigold-deep hover:underline">
                  All {place.approved_observation_count} reports →
                </Link>
              )
            }
          />
          <CategoryTabs
            key={sp.category ?? "all"}
            tabs={reportTabs(checks, themes)}
            allLabel="All local updates"
            initialKey={sp.category ?? null}
            items={checks.slice(0, 12).map((check) => ({
              id: check.observation.observation_id,
              keys: reportTabKeys(check.observation),
              node: <ReportCard check={check} />,
            }))}
            emptyMessages={emptyCategoryMessages}
            defaultEmptyMessage="Nothing reported here yet."
          />
          <div className="mt-5 space-y-1 text-xs text-ink-faint">
            <p>Dates describe visits, not today&rsquo;s guarantees.</p>
            {unreported.length > 0 && <p>No recent reports on: {unreported.join(", ")}.</p>}
          </div>
          <div className="mt-10">
            <AskAboutPlace placeName={place.name} conditions={place.conditions} observations={place.recent_observations} />
          </div>
        </Section>
      )}

      {show.verified && (
        <Section id="verified">
          <PlaceSectionHeading
            kind="verified"
            eyebrow="Verified by TrailMind guides"
            title="Key facts, confirmed on the ground"
            intro="Each fact was confirmed by a guide's reviewed report, and shows when — facts expire and get re-checked."
          />
          <VerifiedKnowledge categories={verified} />
        </Section>
      )}

      {show.answers && (
        <Section id="answers">
          <PlaceSectionHeading
            kind="live"
            eyebrow="The questions people ask here"
            title="Current answers, with local context"
            intro="Who answered, and when they visited."
          />
          <PopularQuestionsSection questions={place.popular_questions} />
        </Section>
      )}

      {show.route && place.route && (
        <Section id="route">
          <PlaceSectionHeading
            eyebrow="The route strip"
            title={place.route.name}
            intro={place.route.description ?? "Every stop on this route, and when a guide last reported there."}
          />
          <RouteStrip route={place.route} currentLocationId={place.location_id} />
        </Section>
      )}

      {show.bearings && (
        <Section id="bearings" band>
          <PlaceSectionHeading
            eyebrow="Get your bearings"
            title={`Explore ${place.name} and nearby`}
            intro="The places closest to here, grouped by what they are. Open one for its own reports."
          />
          <CategoryTabs
            tabs={bearingTabs}
            allLabel="All places"
            items={place.nearby.map((p) => ({ id: p.location_id, keys: themeKeysOf(p), node: <PlaceCard place={p} /> }))}
            defaultEmptyMessage="No nearby places in this category."
          />
        </Section>
      )}

      {show.media && (
        <Section id="photos">
          <PlaceSectionHeading
            kind="live"
            eyebrow="A closer look"
            title="From guides' visits"
            aside={
              place.photo_count > 4 && (
                <Link href={`/places/${place.location_id}/photos`} className="text-sm font-semibold text-marigold-deep hover:underline">
                  See all {place.photo_count} photos →
                </Link>
              )
            }
          />
          <div className="space-y-8">
            {place.photo_count > 0 && <PhotoGrid observations={place.recent_observations.slice(0, 8)} />}
            {voiceStory && (
              <VoicePlayer audioUrl={voiceStory.audio_url} transcript={voiceStory.transcript} guideName={voiceStory.guide_name} />
            )}
          </div>
        </Section>
      )}

      {show.sources && (
        <Section id="sources">
          <PlaceSectionHeading eyebrow="Sources & contributors" title="Where this page comes from" />
          <SourcesAndContributors summary={research} guideNames={guideNames} />
        </Section>
      )}
    </div>
  );
}
