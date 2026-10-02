import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { content } from "@/lib/content";
import type { PublicLocationSummary } from "@/lib/content";
import { AskAboutPlace } from "@/components/AskAboutPlace";
import { SafetyBanner } from "@/components/SafetyBanner";
import { buildLocalChecks, primaryPlaceType, reportTabKeys, reportTabs, themeCategories, verifiedCategories } from "@/lib/content/locationPage";
import { cleanDescription, dateTime, formatMeters, groupPlaces, nowMs, placeTypeOf, routeNeighbours } from "@/lib/content/guide";
import { PageHero, LatestCheck, type HeroVisual } from "@/components/guide/PageHero";
import { SectionNav } from "@/components/guide/SectionNav";
import { SectionHeader, Note, TextLink } from "@/components/guide/primitives";
import { FilterGrid } from "@/components/guide/FilterGrid";
import { ReportCard } from "@/components/guide/ReportCard";
import { QuestionsSection } from "@/components/guide/Questions";
import { GroupedExplorer } from "@/components/guide/GroupedExplorer";
import { PlaceCard, PlaceFeature } from "@/components/guide/PlaceCards";
import { Band, FindingAccordions, JourneySteps, PlanningHeader, ResearchEssay } from "@/components/guide/Planning";
import { ExploreCards, GuideVoices, OrientationPanel, PhotoStrip, SourcesSection, VerifiedTable, type ExploreCard, type Orientation } from "@/components/guide/Blocks";
import { RouteFeature } from "@/components/guide/RouteFeature";
import { Icon } from "@/components/guide/Icons";

export async function generateMetadata({ params }: { params: Promise<{ locationId: string }> }): Promise<Metadata> {
  const { locationId } = await params;
  const place = await content.getLocation(locationId);
  if (!place) return {};
  return {
    title: place.is_area_hub ? `${place.name} area guide` : place.name,
    description: cleanDescription(place.description) ?? place.research_summary?.known_for ?? `Local guide reports, questions and background for ${place.name}.`,
  };
}

function Section({ id, children, className = "" }: { id?: string; children: React.ReactNode; className?: string }) {
  return (
    <section id={id} className={`page scroll-mt-[76px] py-14 sm:py-16 ${className}`}>
      {children}
    </section>
  );
}

function themeList(place: PublicLocationSummary, n = 3): string {
  return (place.categories ?? [])
    .filter((c) => c.kind === "theme")
    .slice(0, n)
    .map((c) => c.display_name)
    .join(" · ");
}

/**
 * A complete place guide, in the reference guide's order and rhythm:
 * identity -> the local field notebook -> orientation -> the questions people
 * ask -> verified facts -> exploring the area -> a closer look -> the
 * planning foundations (route + research) -> journeys -> where next -> ask ->
 * sources. Every block renders only from real data and names what it is.
 */
export default async function PlacePage({ params }: { params: Promise<{ locationId: string }> }) {
  const { locationId } = await params;
  const place = await content.getLocation(locationId);
  if (!place) notFound();

  const now = nowMs();
  const research = place.research_summary?.status === "completed" ? place.research_summary : null;
  const themes = themeCategories(place.categories);
  const verified = verifiedCategories(place.categories);
  const checks = buildLocalChecks(place.recent_observations, place.conditions, place.categories);
  const hub = place.is_area_hub ? place : (place.nearby.find((n) => n.is_area_hub) ?? null);
  const route = place.route && place.route.stops.length > 0 ? place.route : null;
  const position = route ? routeNeighbours(route, place.location_id) : null;
  const placeType = primaryPlaceType(place.categories);
  const description = cleanDescription(place.description);
  const guideNames = [
    ...new Set([...place.recent_observations.map((o) => o.guide_name), ...place.popular_questions.flatMap((q) => q.answers.map((a) => a.guide_name))]),
  ];
  const questionCount = place.popular_questions.length + place.open_questions.length;
  const photoObs = place.recent_observations.filter((o) => o.photo_urls[0]);
  const voiceObs = place.recent_observations.filter((o) => o.transcript);
  const groups = groupPlaces(place.nearby);
  const reportTabsList = reportTabs(checks, themes).filter((t) => t.count > 0);
  const askHref = "#ask";

  const lede =
    description ??
    research?.description ??
    research?.known_for ??
    (place.nearby.length > 0
      ? `${place.is_area_hub ? "An area" : "A place"} with ${place.nearby.length} places within walking distance${questionCount ? ` and ${questionCount} questions travellers ask` : ""}. Local guide reports, open questions and background research, each clearly marked.`
      : null);
  const ledeFromResearch = !description && research ? (research.description ? "description" : research.known_for ? "known_for" : null) : null;

  const visual: HeroVisual = photoObs[0]
    ? { kind: "photo", url: photoObs[0].photo_urls[0]!, caption: photoObs[0].location_label ?? place.name, tag: `Guide photo · ${dateTime(photoObs[0].observed_at)}` }
    : {
        kind: "map",
        center: { latitude: place.latitude, longitude: place.longitude, label: place.name },
        pins: place.nearby.slice(0, 12).map((n) => ({ latitude: n.latitude, longitude: n.longitude, label: n.name })),
        caption: place.name,
        zoom: place.is_area_hub ? 15 : 16,
      };

  const breadcrumb = [
    { label: "Explore", href: "/explore" },
    ...(route ? [{ label: route.name, href: `/routes/${route.slug}` }] : []),
    ...(hub && hub.location_id !== place.location_id ? [{ label: hub.name, href: `/places/${hub.location_id}` }] : []),
    { label: place.name },
  ];

  const show = {
    latest: true,
    answers: questionCount > 0,
    verified: verified.length > 0,
    explore: place.nearby.length > 0,
    photos: photoObs.length > 0,
    voices: voiceObs.length > 0,
    plan: Boolean(position?.current || research || place.research_findings.length),
  };
  const nav = [
    { id: "latest", label: "Latest checks" },
    show.answers && { id: "answers", label: "Current answers" },
    show.verified && { id: "verified", label: "Verified facts" },
    show.explore && { id: "explore", label: `Explore ${place.name}` },
    show.photos && { id: "photos", label: "Photos" },
    show.plan && { id: "plan", label: "Plan your visit" },
    { id: "sources", label: "Sources" },
  ].filter(Boolean) as { id: string; label: string }[];

  const orientation: Orientation[] = [
    questionCount > 0 && {
      icon: "chat",
      title: "What do travellers ask here?",
      text: `${questionCount} question${questionCount === 1 ? "" : "s"} about ${place.name}${place.popular_questions.length ? `, ${place.popular_questions.length} answered by a local guide` : ""}.`,
      link: { href: "#answers", label: "Read the questions" },
    },
    place.nearby.length > 0 && {
      icon: "compass",
      title: `A little time around ${place.name}?`,
      text: `${place.nearby.length} places within walking distance${groups[0] ? ` — ${groups.slice(0, 3).map((g) => g.label.toLowerCase()).join(", ")}` : ""}.`,
      link: { href: "#explore", label: `Explore ${place.name}` },
    },
    position?.next
      ? {
          icon: "boots",
          title: "Ready to start walking?",
          text: `${place.name} is stop ${position.index + 1} of ${position.stops.length} on the ${route!.name}. Next: ${position.next.name}.`,
          link: { href: `/places/${position.next.location_id}`, label: `Continue to ${position.next.name}` },
        }
      : route
        ? { icon: "route", title: `On the ${route.name}`, text: `See every stop and when a guide last checked it.`, link: { href: `/routes/${route.slug}`, label: "Follow the route" } }
        : null,
  ].filter(Boolean) as Orientation[];

  const exploreCards: ExploreCard[] = [
    route && {
      eyebrow: "Follow the route",
      title: route.name,
      text: `${route.stops.length} stops, ${position?.current ? `from stop ${position.index + 1}` : "stop by stop"}.`,
      href: `/routes/${route.slug}`,
      map: { latitude: route.stops[Math.floor(route.stops.length / 2)].latitude, longitude: route.stops[Math.floor(route.stops.length / 2)].longitude },
      zoom: 11,
    },
    position?.next && {
      eyebrow: "Walk onward",
      title: position.next.name,
      text: position.next.elevation_meters ? `The next stop, at ${position.next.elevation_meters.toLocaleString()} m.` : "The next stop on the route.",
      href: `/places/${position.next.location_id}`,
      map: { latitude: position.next.latitude, longitude: position.next.longitude },
      zoom: 14,
    },
    hub && hub.location_id !== place.location_id && {
      eyebrow: "Zoom out",
      title: `The ${hub.name} area`,
      text: "Every place, question and report around it.",
      href: `/places/${hub.location_id}`,
      map: { latitude: hub.latitude, longitude: hub.longitude },
      zoom: 14,
    },
    {
      eyebrow: "Keep exploring",
      title: "Every place we cover",
      text: "Compare areas, routes and the latest reports.",
      href: "/explore",
      map: { latitude: place.latitude, longitude: place.longitude },
      zoom: 9,
    },
  ]
    .filter(Boolean)
    .slice(0, 3) as ExploreCard[];

  return (
    <div>
      <PageHero
        breadcrumb={breadcrumb}
        eyebrow={place.is_area_hub ? "An area guide" : `${placeType ?? "Place"}${hub && hub.location_id !== place.location_id ? ` · ${hub.name}` : ""}`}
        title={place.name}
        subtitle={position?.current ? `Stop ${position.index + 1} of ${position.stops.length} on the ${route!.name}` : themeList(place) || null}
        lede={lede}
        status={
          <LatestCheck
            at={place.last_activity_at ? dateTime(place.last_activity_at) : null}
            detail={
              guideNames.length > 0
                ? `${guideNames.length} contributing guide${guideNames.length === 1 ? "" : "s"} · ${place.approved_observation_count} local report${place.approved_observation_count === 1 ? "" : "s"}`
                : questionCount > 0
                  ? `${questionCount} questions waiting for a local check`
                  : null
            }
          />
        }
        visual={visual}
      />

      <SectionNav items={nav} label={place.is_area_hub ? "In this area" : "On this page"} action={{ href: askHref, label: "Ask a guide" }} />

      <div className="page">
        <SafetyBanner conditions={place.conditions} observations={place.recent_observations} />
      </div>

      <Section id="latest">
        <SectionHeader
          eyebrow="The local field notebook"
          title={`The latest around ${place.name}`}
          intro={checks.length > 0 ? "Dated reports from local guides' recent visits, newest first." : undefined}
          aside={<TextLink href="/#trust" icon="info" className="!font-normal !text-ink-soft">How we report</TextLink>}
        />
        {checks.length > 0 ? (
          <FilterGrid
            tabs={reportTabsList.map((t) => ({ key: t.key, label: t.label }))}
            allLabel="All local updates"
            trailing="Observed, dated, attributed."
            items={checks.map((check) => ({
              id: check.observation.observation_id,
              keys: reportTabKeys(check.observation),
              node: <ReportCard check={check} showPlace={place.name} />,
            }))}
            initialVisible={3}
            footnote="local reports · dates describe visits, not today's guarantees"
            emptyMessage="Nothing reported in this category yet."
          />
        ) : (
          <div className="flex flex-wrap items-center gap-5 rounded-[8px] border border-dashed border-border-strong px-7 py-7">
            <Icon name="clock" size={26} strokeWidth={1.5} className="text-ink-faint" />
            <div className="min-w-0 flex-1">
              <p className="text-[17px] font-bold text-ink">No guide has reported from {place.name} yet.</p>
              <p className="mt-1 text-[15px] text-ink-soft">
                When a local guide visits, their dated report appears here first. Until then, everything below is background, open questions or nearby places.
              </p>
            </div>
            <TextLink href={askHref} icon="chat">Ask for a local check</TextLink>
          </div>
        )}
        {orientation.length > 0 && (
          <div className="mt-12">
            <OrientationPanel items={orientation} />
          </div>
        )}
      </Section>

      {show.answers && (
        <Section id="answers" className="!pt-4">
          <SectionHeader
            eyebrow="The questions people ask here"
            title="Current answers, with local context"
            intro="Who checked, when they visited — and which questions are still waiting for a local check."
          />
          <QuestionsSection placeName={place.name} answered={place.popular_questions} open={place.open_questions} guideNames={guideNames} askHref={askHref} nowMs={now} />
          <Note className="mt-6">
            Answers describe one guide&rsquo;s visit on the date shown. An unanswered question means nobody has checked it yet — not that there is no answer.
          </Note>
        </Section>
      )}

      {show.verified && (
        <Section id="verified" className="!pt-4">
          <SectionHeader
            eyebrow="What local guides have confirmed"
            title={`Key facts about ${place.name}`}
            intro="Each fact was confirmed by a reviewed guide report, and shows when — facts expire and get re-checked."
          />
          <VerifiedTable categories={verified} />
        </Section>
      )}

      {show.explore && (
        <Section id="explore" className="!pt-4">
          <SectionHeader
            eyebrow="Get your bearings"
            title={`Explore ${place.name} and nearby`}
            intro="Start with what you need, then open a place for its own reports and questions."
          />
          <GroupedExplorer
            allLabel="All places"
            groups={groups.map((g) => ({
              key: g.key,
              label: g.label,
              count: g.places.length,
              content:
                g.places.length === 1 ? (
                  <PlaceFeature place={g.places[0]} eyebrow={`${placeTypeOf(g.places[0]) ?? "Place"} · ${formatMeters(g.places[0].distance_meters) ?? ""} away`} />
                ) : (
                  <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                    {g.places.map((p) => (
                      <div key={p.location_id} className="flex">
                        <PlaceCard place={p} origin={place.name} />
                      </div>
                    ))}
                  </div>
                ),
            }))}
          />
        </Section>
      )}

      {show.voices && (
        <Section className="!pt-4">
          <SectionHeader eyebrow="Experience that stays useful" title="A little advice from the people who walk here" />
          <GuideVoices observations={voiceObs} />
        </Section>
      )}

      {show.photos && (
        <Section id="photos" className="!pt-4">
          <SectionHeader eyebrow="A closer look" title={`From guides' visits to ${place.name}`} intro="Photos attached to dated guide reports." />
          <PhotoStrip observations={photoObs} />
        </Section>
      )}

      {show.plan && (
        <Band id="plan">
          <PlanningHeader name={place.name} />
          <div className="space-y-12">
            {route && <JourneySteps route={route} locationId={place.location_id} />}
            {research && <ResearchEssay summary={research} skip={ledeFromResearch} />}
            {place.research_findings.length > 0 && (
              <div>
                <p className="mb-2 flex items-center gap-2 text-[13px] text-ink-meta">
                  <Icon name="book" size={15} /> Background research from public web sources — what sources claim, not a guide&rsquo;s check.
                </p>
                <FindingAccordions findings={place.research_findings} />
              </div>
            )}
          </div>
        </Band>
      )}

      {route && (
        <Section className="!pb-4">
          <SectionHeader eyebrow="Journeys that pass through here" title={`${place.name} is part of the ${route.name}`} />
          <RouteFeature route={route} highlightId={place.location_id} />
        </Section>
      )}

      <Section>
        <SectionHeader eyebrow="Keep exploring" title="Where will you go from here?" />
        <ExploreCards cards={exploreCards} />
      </Section>

      <section id="ask" className="page scroll-mt-[76px] pb-14">
        <div className="grid gap-8 rounded-[8px] bg-deep px-7 py-10 text-white sm:px-11 lg:grid-cols-[1fr_1.1fr] lg:items-center">
          <div>
            <p className="text-[11.5px] font-bold uppercase tracking-[0.14em] text-[#9fd3e2]">Start with a local question</p>
            <h2 className="mt-3 text-[28px] font-bold leading-[1.22] tracking-[-0.025em] sm:text-[31px]">
              What would make your time
              <br className="hidden sm:block" /> in {place.name} easier?
            </h2>
            <p className="mt-3 text-[16.5px] leading-[1.7] text-white/85">
              Ask about what guides have reported here. Answers come only from dated reports — never a guess.
            </p>
          </div>
          <AskAboutPlace placeName={place.name} conditions={place.conditions} observations={place.recent_observations} />
        </div>
      </section>

      <Section id="sources" className="!pt-2">
        <SourcesSection
          guideNames={guideNames}
          findings={place.research_findings}
          researchSources={(research?.source_urls ?? []).map((url, i) => ({ url, title: research?.source_titles[i] ?? null }))}
          questionCount={questionCount}
          hubName={hub?.name ?? null}
        />
      </Section>
    </div>
  );
}
