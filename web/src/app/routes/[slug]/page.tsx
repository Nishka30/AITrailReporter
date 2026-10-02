import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { content } from "@/lib/content";
import type { PublicLocationDetail, PublicObservation } from "@/lib/content";
import { buildLocalChecks, reportTabKeys } from "@/lib/content/locationPage";
import { isWithinLastDays, recentDateRangeLabel } from "@/lib/content/freshness";
import { dateTime, nowMs } from "@/lib/content/guide";
import { PageHero, LatestCheck } from "@/components/guide/PageHero";
import { SectionNav } from "@/components/guide/SectionNav";
import { SectionHeader, Note, TextLink } from "@/components/guide/primitives";
import { FilterGrid } from "@/components/guide/FilterGrid";
import { ReportCard } from "@/components/guide/ReportCard";
import { QuestionsSection } from "@/components/guide/Questions";
import { Band } from "@/components/guide/Planning";
import { CtaBand } from "@/components/guide/Blocks";
import { MapTile, MAP_ATTRIBUTION } from "@/components/guide/MapTile";
import { routeCenter, routeZoom, routeScale, elevationRange } from "@/components/guide/RouteFeature";
import { ElevationProfile, GuideCards, RouteStripPanel, StopCard, WeekDigest, guideStats } from "@/components/guide/RouteParts";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const route = await content.getRoute(slug);
  if (!route) return {};
  return { title: route.name, description: route.description ?? `Every stop on ${route.name}, and what local guides have reported at each.` };
}

function Section({ id, children, className = "" }: { id?: string; children: React.ReactNode; className?: string }) {
  return (
    <section id={id} className={`page scroll-mt-[76px] py-14 sm:py-16 ${className}`}>
      {children}
    </section>
  );
}

const NUMBER_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"];

/**
 * A route as the reference's "route strip" page: identity and the strip of
 * stops up top, then what guides reported along it, the questions asked
 * along it, every stop in order, and the journey's shape (map + elevation).
 * Stops are real RouteStop rows; reports and questions come from each stop's
 * own place page data.
 */
export default async function RoutePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const route = await content.getRoute(slug);
  if (!route) notFound();

  const now = nowMs();
  const stops = [...route.stops].sort((a, b) => a.sequence_order - b.sequence_order);
  const details = await Promise.all(stops.map((s) => content.getLocation(s.location_id)));
  const detailByStop = new Map<string, PublicLocationDetail | null>(stops.map((s, i) => [s.location_id, details[i]]));

  // Each stop's reports, judged against THAT stop's own conditions and
  // categories; a report near two stops is shown once, at the nearer stop.
  const seen = new Set<string>();
  const checks = stops.flatMap((s) => {
    const d = detailByStop.get(s.location_id);
    if (!d) return [];
    return buildLocalChecks(d.recent_observations, d.conditions, d.categories)
      .filter((c) => !seen.has(c.observation.observation_id) && seen.add(c.observation.observation_id))
      .map((check) => ({ check, stop: s }));
  });
  checks.sort((a, b) => +new Date(b.check.observation.observed_at) - +new Date(a.check.observation.observed_at));
  const observations: PublicObservation[] = checks.map((c) => c.check.observation);
  const stopOf = new Map(checks.map((c) => [c.check.observation.observation_id, c.stop.name]));
  const latestByStop = new Map<string, PublicObservation>();
  for (const c of checks) if (!latestByStop.has(c.stop.location_id)) latestByStop.set(c.stop.location_id, c.check.observation);

  const answered = details.flatMap((d) => d?.popular_questions ?? []);
  const open = details.flatMap((d) => d?.open_questions ?? []);
  const guides = guideStats(observations, (o) => stopOf.get(o.observation_id) ?? null);
  const thisWeek = observations.filter((o) => isWithinLastDays(o.observed_at, 7));
  const latest = observations[0] ?? null;
  const range = elevationRange(route);
  const highest = stops.reduce<(typeof stops)[number] | null>((m, s) => (s.elevation_meters != null && (!m || s.elevation_meters > (m.elevation_meters ?? 0)) ? s : m), null);

  const topicTabs = [...new Map(checks.map((c) => [reportTabKeys(c.check.observation)[0], c.check.label])).entries()].map(([key, label]) => ({ key, label }));

  const words = route.name.split(" ");
  const nav = [
    observations.length > 0 && { id: "right-now", label: "Right now" },
    answered.length + open.length > 0 && { id: "answers", label: "Current answers" },
    { id: "stops", label: "The stops" },
    { id: "plan", label: "Plan this trek" },
    guides.length > 0 && { id: "guides", label: "Our guides" },
  ].filter(Boolean) as { id: string; label: string }[];

  return (
    <div>
      <PageHero
        breadcrumb={[{ label: "Explore", href: "/explore" }, { label: "Routes", href: "/routes" }, { label: route.name }]}
        eyebrow="The route, through local eyes"
        title={words.length > 1 ? words.slice(0, -1).join(" ") : route.name}
        titleAccent={words.length > 1 ? words[words.length - 1] : undefined}
        lede={route.description}
        meta={[
          stops.length > 1 ? { icon: "route" as const, text: `${stops[0].name} → ${stops[stops.length - 1].name}` } : null,
          { icon: "pin" as const, text: `${stops.length} stop${stops.length === 1 ? "" : "s"}` },
          highest ? { icon: "mountain" as const, text: `Highest: ${highest.name}, ${highest.elevation_meters!.toLocaleString()} m` } : null,
        ].filter((m): m is NonNullable<typeof m> => Boolean(m))}
        status={
          <LatestCheck
            at={latest ? dateTime(latest.observed_at) : null}
            detail={observations.length ? `${guides.length} guide${guides.length === 1 ? "" : "s"} · ${observations.length} route report${observations.length === 1 ? "" : "s"}` : null}
          />
        }
        visual={{
          kind: "map",
          center: { ...routeCenter(route), label: route.name },
          pins: stops.map((s) => ({ latitude: s.latitude, longitude: s.longitude, label: s.name })),
          caption: `${stops[0]?.name ?? ""}${stops.length > 1 ? ` to ${stops[stops.length - 1].name}` : ""}`,
          zoom: routeZoom(route),
          line: true,
          scale: routeScale(route),
        }}
      />

      <div className="page -mt-4 pb-10">
        <RouteStripPanel route={route} guideByStop={Object.fromEntries([...latestByStop.entries()].map(([id, o]) => [id, o.guide_name]))} />
      </div>

      <SectionNav items={nav} action={{ href: "#ask", label: "Ask a guide" }} />

      {observations.length > 0 && (
        <Section id="right-now">
          <SectionHeader
            title={`Right now on the ${route.name}`}
            intro="Dated reports from guides along the route, newest first."
            aside={<TextLink href="/#trust" icon="info" className="!font-normal !text-ink-soft">How we report</TextLink>}
          />
          <FilterGrid
            tabs={topicTabs}
            allLabel="All topics"
            trailing="Observed, dated, attributed."
            items={checks.map(({ check, stop }) => ({
              id: check.observation.observation_id,
              keys: reportTabKeys(check.observation),
              node: <ReportCard check={check} showPlace={stop.name} />,
            }))}
            initialVisible={3}
            moreLabel="See more route reports"
            footnote="selected field reports"
            emptyMessage="Nothing reported on this topic yet."
          />
          {thisWeek.length > 0 && (
            <div className="mt-14">
              <WeekDigest
                title={
                  <>
                    This week
                    <br />
                    on the trail.
                  </>
                }
                range={recentDateRangeLabel(7)}
                observations={thisWeek}
              />
            </div>
          )}
        </Section>
      )}

      {answered.length + open.length > 0 && (
        <Section id="answers" className="!pt-4">
          <SectionHeader eyebrow="Before your next walking day" title="Current answers, with the evidence" intro="Practical answers with their dates — and the questions still waiting for a local check." />
          <QuestionsSection placeName="the trek" answered={answered} open={open} guideNames={guides.map((g) => g.name)} askHref="#ask" nowMs={now} />
        </Section>
      )}

      <Section id="stops" className="!pt-4">
        <SectionHeader
          eyebrow="Get to know the journey"
          title={`${NUMBER_WORDS[stops.length] ?? stops.length} stop${stops.length === 1 ? "" : "s"}, in the order you reach them.`}
          intro="Open a stop for its own field notebook, questions and nearby places."
        />
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {stops.map((s) => (
            <div key={s.route_stop_id} className="flex">
              <StopCard stop={s} detail={detailByStop.get(s.location_id) ?? null} latest={latestByStop.get(s.location_id) ?? null} />
            </div>
          ))}
        </div>
      </Section>

      <Band id="plan">
        <SectionHeader
          eyebrow="Route reference · the planning foundations"
          title="Plan the journey, not just the destination."
          intro="The shape of the route, kept separate from the dated observations above."
        />
        <div className="overflow-hidden rounded-[8px] border border-border bg-white">
          <div className="border-b border-border-soft px-7 py-6">
            <p className="text-[11.5px] font-semibold uppercase tracking-[0.14em] text-ink-meta">The outward journey</p>
            <h3 className="mt-2 text-[22px] font-bold tracking-[-0.02em] text-ink">The route and its elevations</h3>
            <p className="mt-1.5 text-[15px] text-ink-soft">Follow the valley on the map, then see how the altitude changes{range ? ` (${range})` : ""}.</p>
          </div>
          <div className="grid md:grid-cols-2">
            <div className="border-b border-border-soft md:border-b-0 md:border-r">
              <div className="flex items-center justify-between px-6 pt-5 text-[14px]">
                <span className="font-semibold text-ink">{stops[0]?.name}{stops.length > 1 ? ` to ${stops[stops.length - 1].name}` : ""}</span>
                <span className="text-[12.5px] text-ink-faint">{MAP_ATTRIBUTION}</span>
              </div>
              <MapTile
                center={routeCenter(route)}
                pins={stops.map((s) => ({ latitude: s.latitude, longitude: s.longitude, label: s.name }))}
                zoom={routeZoom(route)}
                centerMarker={false}
                line
                scale={routeScale(route)}
                className="relative m-5 h-[340px] rounded-[6px]"
              />
            </div>
            <div className="px-6 pb-4 pt-5">
              <div className="flex items-center justify-between text-[14px]">
                <span className="font-semibold text-ink">Elevation along the route</span>
                <span className="text-[12.5px] text-ink-faint">Metres · recorded stop elevations</span>
              </div>
              <div className="mt-4">
                <ElevationProfile stops={stops} />
              </div>
              <p className="text-[12.5px] text-ink-faint">Stops are evenly spaced — spacing is not walking distance.</p>
            </div>
          </div>
        </div>
        <Note className="mt-6">Orientation only, not for navigation. Elevations are the recorded stop elevations; local measurements vary.</Note>
      </Band>

      {guides.length > 0 && (
        <Section id="guides">
          <SectionHeader eyebrow="The people behind the notebook" title="Guides reporting along this route" intro="Every report on this route is attributed to the guide who filed it." />
          <GuideCards guides={guides} />
        </Section>
      )}

      <section id="ask" className="page scroll-mt-[76px] pb-16">
        <CtaBand
          eyebrow="Your route. Your questions."
          title={
            <>
              What would help you
              <br className="hidden sm:block" /> feel ready for this trek?
            </>
          }
          text="Ask about a particular stop, the pace, or the details no itinerary quite answers."
          href={stops[0] ? `/places/${stops[0].location_id}#ask` : "/#ask"}
          button="Ask a local guide"
          caption="A question is a good place to start. No booking needed."
        />
      </section>
    </div>
  );
}
