import type { Metadata } from "next";
import { content } from "@/lib/content";
import type { PublicRoute } from "@/lib/content";
import { Breadcrumb, SectionHeader } from "@/components/guide/primitives";
import { RouteFeature } from "@/components/guide/RouteFeature";

export const metadata: Metadata = { title: "Routes" };

export default async function RoutesPage() {
  const summaries = await content.listRoutes();
  const routes = (await Promise.all(summaries.map((r) => content.getRoute(r.slug)))).filter((r): r is PublicRoute => Boolean(r && r.stops.length));

  return (
    <div className="page pb-20 pt-7">
      <Breadcrumb items={[{ label: "Explore", href: "/explore" }, { label: "Routes" }]} />
      <div className="mt-6">
        <SectionHeader
          eyebrow="Put the places together"
          title="Routes, stop by stop"
          intro="Follow a journey from place to place, with the latest guide check at every stop."
        />
      </div>
      {routes.length > 0 ? (
        <div className="space-y-8">
          {routes.map((r) => (
            <RouteFeature key={r.route_id} route={r} />
          ))}
        </div>
      ) : (
        <p className="rounded-[8px] border border-dashed border-border-strong px-6 py-8 text-[15px] text-ink-soft">
          No routes have been mapped yet. They appear here as soon as their stops exist.
        </p>
      )}
    </div>
  );
}
