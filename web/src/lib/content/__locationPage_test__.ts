/**
 * Pure-logic tests for locationPage.ts -- plain Node via `npx tsx`, same
 * pattern as __mockRouteStatus_test__.ts (web/ has no test framework).
 */
import {
  CONDITIONS_TAB,
  buildLocalChecks,
  placeTabs,
  placeTypeOf,
  primaryPlaceType,
  reportTabs,
  themeCategories,
  themeKeysOf,
  unreportedConditionNames,
  unverifiedThemeNames,
  verifiedCategories,
} from "./locationPage";
import type { PublicConditionState, PublicLocationCategory, PublicLocationSummary, PublicObservation } from "./types";

let failures = 0;
function check(label: string, cond: boolean, extra: string = ""): void {
  console.log(`[${cond ? "PASS" : "FAIL"}] ${label} ${extra}`);
  if (!cond) failures++;
}

const iso = (hoursAgo: number) => new Date(Date.now() - hoursAgo * 3_600_000).toISOString();

function obs(id: string, knowledgeType: string, hoursAgo: number, category?: [string, string]): PublicObservation {
  return {
    observation_id: id,
    knowledge_type: category ? category[0] : knowledgeType,
    display_name: category ? category[1] : knowledgeType,
    safety_critical: false,
    value: {},
    evidence: null,
    observed_at: iso(hoursAgo),
    submission_type: "text",
    guide_name: "Pemba",
    has_photo: false,
    has_audio: false,
    photo_urls: [],
    audio_url: null,
    transcript: null,
    nearest_place_id: null,
    nearest_place_name: null,
    category_slug: category ? category[0] : null,
    category_display_name: category ? category[1] : null,
  };
}

function condition(knowledgeType: string, state: PublicConditionState["state"], latestId: string | null): PublicConditionState {
  return {
    knowledge_type: knowledgeType,
    display_name: knowledgeType,
    safety_critical: false,
    state,
    observed_at: null,
    age_hours: null,
    severity_hours: 0,
    latest_observation_id: latestId,
  };
}

function category(slug: string, kind: string, state: PublicLocationCategory["state"], verified = 0, isPrimary = false): PublicLocationCategory {
  return {
    slug,
    kind,
    display_name: slug,
    relevance: 80,
    is_primary: isPrimary,
    state,
    verified_knowledge: Array.from({ length: verified }, (_, i) => ({
      knowledge_id: `${slug}-${i}`,
      knowledge_text: "fact",
      last_verified_at: iso(1),
      fresh: true,
    })),
  };
}

function run() {
  console.log("=== locationPage.ts ===");

  const cats = [
    category("area", "place_type", "missing", 0, true),
    category("lodging", "theme", "fresh", 1),
    category("trekking", "theme", "missing"),
  ];
  check("themes exclude place_type", themeCategories(cats).map((c) => c.slug).join() === "lodging,trekking");
  check("primary place type is the identity", primaryPlaceType(cats) === "area");
  check("no place_type -> null", primaryPlaceType([category("lodging", "theme", "fresh")]) === null);
  check("verified categories only", verifiedCategories(cats).map((c) => c.slug).join() === "lodging");
  check("unverified theme names", unverifiedThemeNames(cats).join() === "trekking");

  const observations = [
    obs("trail-old", "trail_condition", 50),
    obs("trail-new", "trail_condition", 5),
    obs("lodge-new", "", 2, ["lodging", "Lodging"]),
    obs("lodge-old", "", 40, ["lodging", "Lodging"]),
  ];
  const conditions = [condition("trail_condition", "aging", "trail-new"), condition("weather", "missing", null)];
  const checks = buildLocalChecks(observations, conditions, cats);
  const stateOf = (id: string) => checks.find((c) => c.observation.observation_id === id)?.state;

  check("newest first", checks.map((c) => c.observation.observation_id).join() === "lodge-new,trail-new,lodge-old,trail-old");
  check("latest hazard report takes the live condition state", stateOf("trail-new") === "aging");
  check("older hazard report is superseded, never current", stateOf("trail-old") === "superseded");
  check("latest category report takes the category state", stateOf("lodge-new") === "fresh");
  check("older category report is superseded", stateOf("lodge-old") === "superseded");
  check("category report labelled by its DB category", checks[0].label === "Lodging");

  const filtered = buildLocalChecks(observations, conditions, cats, "lodging");
  check(
    "category filter keeps only that category, and its latest stays latest",
    filtered.map((c) => `${c.observation.observation_id}:${c.state}`).join() === "lodge-new:fresh,lodge-old:superseded",
  );

  const orphan = buildLocalChecks([obs("x", "", 1, ["gone", "Gone"])], [], []);
  check("category report with no active category is never shown as fresh", orphan[0].state === "stale");

  check("unreported hazard names", unreportedConditionNames(conditions).join() === "weather");

  const tabs = reportTabs(checks, themeCategories(cats));
  check(
    "report tabs: every DB theme (even empty) + conditions tab with counts",
    tabs.map((t) => `${t.key}:${t.count}`).join() === "lodging:2,trekking:0,conditions:2",
  );
  check("no conditions tab without hazard reports", !reportTabs(checks.filter((c) => c.observation.category_slug), []).some((t) => t.key === CONDITIONS_TAB));

  const place = (id: string, themes: string[], placeType = "Shop"): PublicLocationSummary => ({
    location_id: id,
    name: id,
    description: null,
    latitude: 0,
    longitude: 0,
    approved_observation_count: 0,
    last_activity_at: null,
    categories: [{ slug: placeType.toLowerCase(), kind: "place_type", display_name: placeType }, ...themes.map((t) => ({ slug: t, kind: "theme", display_name: t }))],
  });
  const places = [place("a", ["transport", "practical"], "Airport"), place("b", ["transport"]), place("c", ["practical"]), place("d", ["lodging"])];
  check("place tabs need >=2 places, most common first", placeTabs(places).map((t) => `${t.key}:${t.count}`).join() === "practical:2,transport:2");
  check("place type is the card identity", placeTypeOf(places[0]) === "Airport");
  check("theme keys exclude place_type", themeKeysOf(places[0]).join() === "transport,practical");
  check("summary without categories (old backend) is safe", placeTypeOf({ ...places[0], categories: undefined }) === null);

  console.log();
  if (failures > 0) {
    console.log(`FAILURES: ${failures}`);
    process.exit(1);
  }
  console.log("ALL PASSED");
}

run();
