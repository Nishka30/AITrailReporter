/**
 * Pure presentation shaping for the Location page -- no fetching, no
 * freshness thresholds. Every state here comes from the backend
 * (evaluate_public_knowledge_state for hazard types, get_location_coverage
 * for categories); this file only decides what goes in which section.
 */
import type {
  CategoryState,
  KnowledgeState,
  PublicConditionState,
  PublicLocationCategory,
  PublicLocationSummary,
  PublicObservation,
} from "./types";

/** Themes (what the place is about) -- the page's category chips. */
export function themeCategories(categories: PublicLocationCategory[]): PublicLocationCategory[] {
  return categories.filter((c) => c.kind === "theme");
}

/** The primary place_type (what the place IS) -- the identity eyebrow. */
export function primaryPlaceType(categories: PublicLocationCategory[]): string | null {
  const primary = categories.find((c) => c.kind === "place_type" && c.is_primary);
  return primary?.display_name ?? categories.find((c) => c.kind === "place_type")?.display_name ?? null;
}

/** Categories that carry at least one TrailMind-verified fact. */
export function verifiedCategories(categories: PublicLocationCategory[]): PublicLocationCategory[] {
  return categories.filter((c) => c.verified_knowledge.length > 0);
}

/** Active theme categories nobody has verified anything for yet. */
export function unverifiedThemeNames(categories: PublicLocationCategory[]): string[] {
  return themeCategories(categories)
    .filter((c) => c.verified_knowledge.length === 0)
    .map((c) => c.display_name);
}

/** "superseded" = an older report of a type/category that has a newer one. */
export type CheckState = KnowledgeState | "superseded";

export interface LocalCheck {
  observation: PublicObservation;
  /** The category this report belongs to (DB category or knowledge type). */
  label: string;
  state: CheckState;
}

function categoryStateToKnowledgeState(state: CategoryState): KnowledgeState {
  switch (state) {
    case "fresh":
      return "fresh";
    case "partially_stale":
      return "aging";
    case "stale":
    // An approved category report always implies verified knowledge; a
    // 'missing' coverage state here can only mean it has since been
    // superseded or retired -- never present it as current.
    case "missing":
      return "stale";
  }
}

/**
 * Each recent report with an honest freshness state:
 *  - the latest report of a hazard knowledge type takes that type's live
 *    condition state;
 *  - the latest report of a category takes its category coverage state;
 *  - every older report of the same type/category is "superseded".
 * With `categorySlug`, only reports verifying that category are kept.
 */
export function buildLocalChecks(
  observations: PublicObservation[],
  conditions: PublicConditionState[],
  categories: PublicLocationCategory[],
  categorySlug: string | null = null,
): LocalCheck[] {
  const conditionByLatestId = new Map(
    conditions.filter((c) => c.latest_observation_id).map((c) => [c.latest_observation_id!, c]),
  );
  const categoryBySlug = new Map(categories.map((c) => [c.slug, c]));
  const seenGroups = new Set<string>();

  const sorted = [...observations].sort((a, b) => +new Date(b.observed_at) - +new Date(a.observed_at));
  const checks: LocalCheck[] = [];
  for (const observation of sorted) {
    const isCategoryReport = Boolean(observation.category_slug);
    const group = isCategoryReport ? `category:${observation.category_slug}` : `type:${observation.knowledge_type}`;
    const isLatestOfGroup = !seenGroups.has(group);
    seenGroups.add(group);

    if (categorySlug && observation.category_slug !== categorySlug) continue;

    let state: CheckState = "superseded";
    if (isLatestOfGroup) {
      if (isCategoryReport) {
        const category = categoryBySlug.get(observation.category_slug!);
        state = category ? categoryStateToKnowledgeState(category.state) : "stale";
      } else {
        state = conditionByLatestId.get(observation.observation_id)?.state ?? "superseded";
      }
    }
    checks.push({
      observation,
      label: observation.category_display_name ?? observation.display_name,
      state,
    });
  }
  return checks;
}

export interface Tab {
  key: string;
  label: string;
  count: number;
}

/** Tab key for hazard/knowledge-type reports, which belong to no DB category. */
export const CONDITIONS_TAB = "conditions";

/** Which tabs a report appears under (besides "All"). */
export function reportTabKeys(observation: PublicObservation): string[] {
  return observation.category_slug ? [observation.category_slug] : [CONDITIONS_TAB];
}

/**
 * Field-notebook tabs: every one of this place's theme categories (from the
 * database, in relevance order -- an empty one still shows, honestly empty),
 * plus one "Trail & weather conditions" tab when hazard reports exist.
 */
export function reportTabs(checks: LocalCheck[], themes: PublicLocationCategory[]): Tab[] {
  const count = (key: string) => checks.filter((c) => reportTabKeys(c.observation).includes(key)).length;
  const tabs: Tab[] = themes.map((t) => ({ key: t.slug, label: t.display_name, count: count(t.slug) }));
  const conditions = count(CONDITIONS_TAB);
  if (conditions > 0) tabs.push({ key: CONDITIONS_TAB, label: "Trail & weather conditions", count: conditions });
  return tabs;
}

/** A place card's identity line: its place_type ("Lodge", "Airport"). */
export function placeTypeOf(place: PublicLocationSummary): string | null {
  return place.categories?.find((c) => c.kind === "place_type")?.display_name ?? null;
}

export function themeKeysOf(place: PublicLocationSummary): string[] {
  return (place.categories ?? []).filter((c) => c.kind === "theme").map((c) => c.slug);
}

/**
 * "Get your bearings" tabs from the nearby places' OWN categories: a theme
 * becomes a tab once at least `minPlaces` places share it (a tab holding one
 * card organises nothing), most common first.
 */
export function placeTabs(places: PublicLocationSummary[], minPlaces = 2, maxTabs = 6): Tab[] {
  const byKey = new Map<string, Tab>();
  for (const place of places) {
    for (const c of place.categories ?? []) {
      if (c.kind !== "theme") continue;
      const tab = byKey.get(c.slug) ?? { key: c.slug, label: c.display_name, count: 0 };
      tab.count += 1;
      byKey.set(c.slug, tab);
    }
  }
  return [...byKey.values()]
    .filter((t) => t.count >= minPlaces)
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
    .slice(0, maxTabs);
}

/** Hazard knowledge types with no report at all nearby -- listed in one
 * quiet line instead of a wall of empty badges. */
export function unreportedConditionNames(conditions: PublicConditionState[]): string[] {
  return conditions.filter((c) => c.state === "missing").map((c) => c.display_name);
}
