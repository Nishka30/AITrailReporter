/**
 * MOCK DATA -- clearly isolated demo content, used only when
 * NEXT_PUBLIC_USE_MOCK_DATA=true (see index.ts). The real dev database
 * currently has just one approved observation, so this file exists purely
 * to make the full product experience visible while it fills up through
 * real admin moderation. Never imported by api.ts, and never presented as
 * if it came from a real contributor -- every mock guide name below is
 * fictional. Photos are generic placeholder imagery (picsum.photos), not
 * real trail photography.
 */
import type {
  CategoryState,
  ContentSource,
  KnowledgeState,
  ListObservationsParams,
  PlaceResearchSummary,
  PublicConditionState,
  PublicKnowledgeType,
  PublicLocationCategory,
  PublicLocationDetail,
  PublicLocationSummary,
  PublicObservation,
  PublicPlaceQuestion,
  PublicRoute,
  PublicRouteStop,
} from "./types";

const HOUR = 60 * 60 * 1000;
const now = () => Date.now();
const hoursAgo = (h: number) => new Date(now() - h * HOUR).toISOString();

const KNOWLEDGE_TYPES: PublicKnowledgeType[] = [
  { knowledge_type: "weather", display_name: "Weather", safety_critical: true },
  { knowledge_type: "trail_condition", display_name: "Trail Condition", safety_critical: false },
  { knowledge_type: "snow_ice", display_name: "Snow / Ice", safety_critical: true },
  { knowledge_type: "obstruction", display_name: "Obstruction", safety_critical: true },
  { knowledge_type: "mobile_signal", display_name: "Mobile Signal", safety_critical: false },
  { knowledge_type: "parking_availability", display_name: "Parking Availability", safety_critical: false },
  { knowledge_type: "water_source", display_name: "Water Source", safety_critical: false },
];

function kt(type: string) {
  return KNOWLEDGE_TYPES.find((k) => k.knowledge_type === type)!;
}

let obsCounter = 0;
function makeObservation(input: {
  location: string;
  knowledgeType: string;
  value: Record<string, unknown>;
  evidence: string;
  hoursAgoObserved: number;
  guideName: string;
  submissionType?: "note" | "voice" | "explore" | "answer";
  photoSeed?: string;
  transcript?: string;
}): PublicObservation {
  obsCounter += 1;
  const type = kt(input.knowledgeType);
  return {
    observation_id: `mock-obs-${input.location}-${obsCounter}`,
    knowledge_type: type.knowledge_type,
    display_name: type.display_name,
    safety_critical: type.safety_critical,
    value: input.value,
    evidence: input.evidence,
    observed_at: hoursAgo(input.hoursAgoObserved),
    submission_type: input.submissionType ?? "note",
    guide_name: input.guideName,
    has_photo: Boolean(input.photoSeed),
    has_audio: Boolean(input.transcript),
    photo_urls: input.photoSeed ? [`https://picsum.photos/seed/${input.photoSeed}/1600/1000`] : [],
    audio_url: null, // no real recording to attach in demo data -- see VoicePlayer's fallback state
    transcript: input.transcript ?? null,
    // Filled in below once LOCATIONS is assembled -- every mock observation's
    // nearest place is trivially the MockLocation it's nested under.
    nearest_place_id: null,
    nearest_place_name: null,
  };
}

function conditionFor(
  observations: PublicObservation[],
  type: PublicKnowledgeType,
  freshnessWindowHours: number,
  agingThresholdHours: number,
): PublicConditionState {
  const relevant = observations
    .filter((o) => o.knowledge_type === type.knowledge_type)
    .sort((a, b) => +new Date(b.observed_at) - +new Date(a.observed_at))[0];

  if (!relevant) {
    return {
      knowledge_type: type.knowledge_type,
      display_name: type.display_name,
      safety_critical: type.safety_critical,
      state: "missing",
      observed_at: null,
      age_hours: null,
      severity_hours: 0,
      latest_observation_id: null,
    };
  }

  const ageHours = (now() - +new Date(relevant.observed_at)) / HOUR;
  const state =
    ageHours <= freshnessWindowHours
      ? "fresh"
      : ageHours <= freshnessWindowHours + agingThresholdHours
        ? "aging"
        : "stale";

  return {
    knowledge_type: type.knowledge_type,
    display_name: type.display_name,
    safety_critical: type.safety_critical,
    state,
    observed_at: relevant.observed_at,
    age_hours: ageHours,
    severity_hours: Math.max(0, ageHours - freshnessWindowHours - agingThresholdHours),
    latest_observation_id: relevant.observation_id,
  };
}

interface MockLocation {
  location_id: string;
  name: string;
  description: string;
  latitude: number;
  longitude: number;
  observations: PublicObservation[];
  /** Optional, mirroring the backend: most mock locations omit these, which
   * demonstrates the same "omit the section entirely" path a real Location
   * with no research/questions yet takes. */
  research?: PlaceResearchSummary;
  questions?: PublicPlaceQuestion[];
  categories?: PublicLocationCategory[];
}

function mockCategory(
  slug: string,
  display_name: string,
  kind: "theme" | "place_type",
  relevance: number,
  verified: { text: string; hoursAgo: number; freshnessHours: number }[] = [],
): PublicLocationCategory {
  const verified_knowledge = verified.map((v, i) => ({
    knowledge_id: `mock-knowledge-${slug}-${i}`,
    knowledge_text: v.text,
    last_verified_at: hoursAgo(v.hoursAgo),
    fresh: v.hoursAgo <= v.freshnessHours,
  }));
  const freshCount = verified_knowledge.filter((k) => k.fresh).length;
  const state: CategoryState =
    verified_knowledge.length === 0
      ? "missing"
      : freshCount === verified_knowledge.length
        ? "fresh"
        : freshCount === 0
          ? "stale"
          : "partially_stale";
  return { slug, display_name, kind, relevance, is_primary: kind === "place_type", state, verified_knowledge };
}

const LOCATIONS: MockLocation[] = [
  {
    location_id: "leh",
    name: "Leh",
    description:
      "The high-desert gateway to Ladakh, 3,500m up -- monasteries, market lanes, and the last reliable mobile signal before the passes.",
    latitude: 34.1526,
    longitude: 77.5771,
    categories: [
      mockCategory("town", "Town", "place_type", 100),
      mockCategory("lodging", "Lodging", "theme", 90, [
        { text: "Guesthouses in the old town have rooms without booking this week.", hoursAgo: 18, freshnessHours: 72 },
        { text: "Hot water is usually solar -- mornings only on cloudy days.", hoursAgo: 200, freshnessHours: 168 },
      ]),
      mockCategory("culture_heritage", "Culture & Heritage", "theme", 85, [
        { text: "Leh Palace is open to visitors; last entry 4:30pm.", hoursAgo: 30, freshnessHours: 336 },
      ]),
      mockCategory("transport", "Transport", "theme", 80),
      mockCategory("local_life", "Local Life", "theme", 65),
    ],
    research: {
      status: "completed",
      description:
        "Leh is the historic capital of Ladakh, built around a 17th-century royal palace modelled on the Potala in Lhasa.",
      known_for: "Its old-town monasteries, market lanes, and rooftop cafes overlooking the palace ridge.",
      highlights: ["Leh Palace", "Shanti Stupa sunrise walk", "Old Town market lanes"],
      things_to_do: [
        "Walk up to Shanti Stupa for sunrise",
        "Explore the old town's market lanes",
        "Acclimatise for a day before heading to the passes",
      ],
      important_facts: ["Elevation: 3,500m", "Last reliable mobile signal before Khardung La"],
      practical_info:
        "Most travellers need at least 24-48 hours here to acclimatise before going higher. ATMs and SIM registration are available in the main market; card payment is patchy outside larger hotels.",
      warnings: ["Altitude sickness risk if you skip acclimatisation -- do not rush straight to the passes."],
      source_urls: ["https://example.com/leh-overview", "https://example.com/leh-practical"],
      source_titles: ["Leh, Ladakh — Overview", "Leh — Practical Notes"],
      researched_at: hoursAgo(96),
    },
    questions: [
      {
        place_question_id: "mock-question-leh-signal",
        question_text: "Is there reliable mobile signal in Leh's old town?",
        context_note: "Guides are frequently asked this before travellers lose signal further up the passes.",
        answers: [
          {
            submission_id: "mock-answer-leh-signal-1",
            answer_text:
              "Yes -- full bars in the main market and old town on BSNL. This is the last strong signal before Khardung La.",
            guide_name: "Namgyal Angchuk",
            answered_at: hoursAgo(20),
          },
        ],
      },
    ],
    observations: [
      makeObservation({
        location: "leh",
        knowledgeType: "weather",
        value: { condition: "clear", temperature_c: 14 },
        evidence: "Clear skies all morning, cold wind picking up after 4pm near the palace ridge.",
        hoursAgoObserved: 3,
        guideName: "Tsering Dolma",
        photoSeed: "leh-palace-1",
      }),
      makeObservation({
        location: "leh",
        knowledgeType: "mobile_signal",
        value: { carrier: "BSNL", strength: "strong" },
        evidence: "Full bars in the main market and old town -- last strong signal before Khardung La.",
        hoursAgoObserved: 20,
        guideName: "Namgyal Angchuk",
      }),
      makeObservation({
        location: "leh",
        knowledgeType: "parking_availability",
        value: { status: "plentiful" },
        evidence: "New taxi stand near the polo ground has space most mornings, fills up by 10am in season.",
        hoursAgoObserved: 30,
        guideName: "Rigzin Chorol",
      }),
      makeObservation({
        location: "leh",
        knowledgeType: "trail_condition",
        value: { condition: "dry", surface: "paved" },
        evidence: "Shanti Stupa steps dry and clear, good grip, popular sunrise walk right now.",
        hoursAgoObserved: 9,
        guideName: "Tsering Dolma",
        submissionType: "voice",
        transcript:
          "We climbed up before sunrise, maybe two hundred steps, nothing technical. The stone was completely dry, no ice this time of year at this elevation. Worth the walk for the light on the mountains alone.",
        photoSeed: "leh-stupa-1",
      }),
    ],
  },
  {
    location_id: "khardung-la",
    name: "Khardung La",
    description:
      "One of the world's highest motorable passes, 5,359m -- weather turns in minutes and the road is the whole story.",
    latitude: 34.2792,
    longitude: 77.6034,
    categories: [
      mockCategory("mountain_pass", "Mountain Pass", "place_type", 100),
      mockCategory("adventure", "Adventure", "theme", 90),
      mockCategory("scenic_spot", "Scenic Spot", "theme", 80),
    ],
    observations: [
      makeObservation({
        location: "khardungla",
        knowledgeType: "snow_ice",
        value: { condition: "packed_snow", extent: "partial" },
        evidence: "Packed snow on the north-facing bend just before the top, chains not needed but slow down.",
        hoursAgoObserved: 6,
        guideName: "Jigmet Wangchuk",
        photoSeed: "khardungla-snow-1",
      }),
      makeObservation({
        location: "khardung-la",
        knowledgeType: "obstruction",
        value: { type: "minor_landslide", lane_impact: "one_lane_open" },
        evidence: "Small rockslide 2km before the summit cafe, BRO already clearing it, one lane moving.",
        hoursAgoObserved: 2,
        guideName: "Stanzin Motup",
        photoSeed: "khardungla-slide-1",
      }),
      makeObservation({
        location: "khardung-la",
        knowledgeType: "weather",
        value: { condition: "windy", temperature_c: -2 },
        evidence: "Sharp wind at the summit marker, most riders not staying more than ten minutes.",
        hoursAgoObserved: 55,
        guideName: "Jigmet Wangchuk",
      }),
    ],
  },
  {
    location_id: "pangong-tso",
    name: "Pangong Tso",
    description:
      "A 135km glacial lake that changes colour through the day -- the water and the shoreline campsites are the whole draw.",
    latitude: 33.7526,
    longitude: 78.5771,
    observations: [
      makeObservation({
        location: "pangong",
        knowledgeType: "weather",
        value: { condition: "clear", temperature_c: 6 },
        evidence: "Water was every shade of blue by 7am, dead calm, best light of the trip so far.",
        hoursAgoObserved: 14,
        guideName: "Deskit Yangzom",
        photoSeed: "pangong-sunrise-1",
      }),
      makeObservation({
        location: "pangong-tso",
        knowledgeType: "mobile_signal",
        value: { carrier: "none", strength: "none" },
        evidence: "No signal at all along the lakeshore camps -- tell travellers to message people before Tangtse.",
        hoursAgoObserved: 40,
        guideName: "Deskit Yangzom",
      }),
      makeObservation({
        location: "pangong-tso",
        knowledgeType: "water_source",
        value: { type: "camp_supplied", potable: true },
        evidence: "Camps near Spangmik supply boiled drinking water, no natural source travellers should drink from directly.",
        hoursAgoObserved: 70,
        guideName: "Konchok Namgyal",
      }),
    ],
  },
  {
    location_id: "nubra-diskit",
    name: "Nubra Valley — Diskit",
    description:
      "Sand dunes, double-humped camels, and the valley floor where the Shyok and Nubra rivers meet.",
    latitude: 34.5333,
    longitude: 77.5667,
    observations: [
      makeObservation({
        location: "nubra",
        knowledgeType: "trail_condition",
        value: { condition: "sandy", surface: "dune" },
        evidence: "Dune walk to the camel point is soft sand the whole way, good shoes recommended, not a hard walk.",
        hoursAgoObserved: 26,
        guideName: "Padma Angmo",
        photoSeed: "nubra-dunes-1",
      }),
      makeObservation({
        location: "nubra-diskit",
        knowledgeType: "weather",
        value: { condition: "warm", temperature_c: 22 },
        evidence: "Noticeably warmer than Leh, sunny all day, good valley for a rest day after the pass.",
        hoursAgoObserved: 48,
        guideName: "Padma Angmo",
        submissionType: "voice",
        transcript:
          "Coming down from Khardung La the temperature just keeps climbing. By the time you reach the valley floor it's a completely different climate, warm enough for short sleeves in the afternoon. A good place to rest a day before heading back up.",
      }),
    ],
  },
  {
    location_id: "zanskar-chadar",
    name: "Zanskar — Chadar Route",
    description: "The frozen-river trek along the Zanskar gorge, walked only when the ice is thick enough to trust.",
    latitude: 33.5000,
    longitude: 76.8833,
    observations: [
      makeObservation({
        location: "zanskar",
        knowledgeType: "snow_ice",
        value: { condition: "thin_ice", extent: "localized" },
        evidence: "Open water and thin ice reported near Tibb cave bend -- local guides rerouting groups around it.",
        hoursAgoObserved: 96,
        guideName: "Sonam Dorjay",
        photoSeed: "zanskar-ice-1",
      }),
    ],
  },
];

for (const loc of LOCATIONS) {
  for (const o of loc.observations) {
    o.nearest_place_id = loc.location_id;
    o.nearest_place_name = loc.name;
  }
}

// Mirrors backend settings.route_stop_freshness_window_hours /
// route_stop_aging_threshold_hours (config.py) -- kept as plain local
// constants rather than importing anything, since this file has no access
// to backend config and is demo data only. Keep these two numbers in sync by
// hand if the backend defaults ever change.
const ROUTE_STOP_FRESHNESS_WINDOW_HOURS = 72;
const ROUTE_STOP_AGING_THRESHOLD_HOURS = 96;

/** Pure function, exported for __mockRouteStatus_test__.ts -- same
 * fresh/aging/stale/missing boundary math as the backend's
 * _bucket_route_stop_freshness, so demo-mode statuses stay consistent with
 * real behaviour. */
export function bucketMockRouteStopFreshness(
  lastActivityAt: string | null,
): { status: KnowledgeState; ageHours: number | null } {
  if (!lastActivityAt) return { status: "missing", ageHours: null };
  const ageHours = (now() - +new Date(lastActivityAt)) / HOUR;
  if (ageHours <= ROUTE_STOP_FRESHNESS_WINDOW_HOURS) return { status: "fresh", ageHours };
  if (ageHours <= ROUTE_STOP_FRESHNESS_WINDOW_HOURS + ROUTE_STOP_AGING_THRESHOLD_HOURS) {
    return { status: "aging", ageHours };
  }
  return { status: "stale", ageHours };
}

function summaryOf(loc: MockLocation): PublicLocationSummary {
  const lastActivity = loc.observations
    .map((o) => +new Date(o.observed_at))
    .sort((a, b) => b - a)[0];
  return {
    location_id: loc.location_id,
    name: loc.name,
    description: loc.description,
    latitude: loc.latitude,
    longitude: loc.longitude,
    approved_observation_count: loc.observations.length,
    last_activity_at: lastActivity ? new Date(lastActivity).toISOString() : null,
    categories: (loc.categories ?? [])
      .slice()
      .sort((a, b) => Number(b.kind === "place_type") - Number(a.kind === "place_type") || b.relevance - a.relevance)
      .map(({ slug, kind, display_name }) => ({ slug, kind, display_name })),
  };
}

function conditionsOf(loc: MockLocation): PublicConditionState[] {
  const windows: Record<string, [number, number]> = {
    weather: [6, 3],
    trail_condition: [72, 24],
    snow_ice: [24, 12],
    obstruction: [168, 72],
    mobile_signal: [72, 24],
    parking_availability: [72, 24],
    water_source: [168, 72],
  };
  return KNOWLEDGE_TYPES.map((type) => {
    const [freshness, aging] = windows[type.knowledge_type];
    return conditionFor(loc.observations, type, freshness, aging);
  });
}

// One example route, reusing EXISTING mock locations (Leh -> Khardung La ->
// Nubra Valley) rather than inventing Everest-specific demo content -- the
// real Everest route is seeded server-side (scripts/seed_routes.py) and only
// appears when NEXT_PUBLIC_USE_MOCK_DATA is false.
const ROUTE_STOP_LOCATION_IDS = ["leh", "khardung-la", "nubra-diskit"] as const;
const ROUTE_STOP_ELEVATIONS: Record<string, number> = {
  leh: 3500,
  "khardung-la": 5359,
  "nubra-diskit": 3144,
};

function buildMockRoute(): PublicRoute {
  const stops: PublicRouteStop[] = ROUTE_STOP_LOCATION_IDS.map((locationId, index) => {
    const loc = LOCATIONS.find((l) => l.location_id === locationId)!;
    const summary = summaryOf(loc);
    const { status, ageHours } = bucketMockRouteStopFreshness(summary.last_activity_at);
    return {
      route_stop_id: `mock-route-stop-${locationId}`,
      location_id: loc.location_id,
      name: loc.name,
      sequence_order: index + 1,
      stop_label: null,
      elevation_meters: ROUTE_STOP_ELEVATIONS[locationId] ?? null,
      latitude: loc.latitude,
      longitude: loc.longitude,
      status,
      last_observed_at: summary.last_activity_at,
      age_hours: ageHours,
    };
  });
  return {
    route_id: "mock-route-leh-nubra",
    slug: "leh-khardung-la-nubra-valley",
    name: "Leh to Nubra Valley via Khardung La",
    description: "The classic high-pass crossing from Leh into the Nubra Valley.",
    stops,
  };
}

const MOCK_ROUTE = buildMockRoute();

// Mirrors backend settings.public_nearby_radius_meters / public_nearby_limit.
const NEARBY_RADIUS_METERS = 20_000;
const NEARBY_LIMIT = 8;

function distanceMeters(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const rad = Math.PI / 180;
  const dLat = (bLat - aLat) * rad;
  const dLng = (bLng - aLng) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(aLat * rad) * Math.cos(bLat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.sqrt(h));
}

function nearbyOf(loc: MockLocation): PublicLocationSummary[] {
  return LOCATIONS.filter((l) => l.location_id !== loc.location_id)
    .map((l) => ({ ...summaryOf(l), distance_meters: distanceMeters(loc.latitude, loc.longitude, l.latitude, l.longitude) }))
    .filter((l) => l.distance_meters <= NEARBY_RADIUS_METERS)
    .sort((a, b) => a.distance_meters - b.distance_meters)
    .slice(0, NEARBY_LIMIT);
}

export const mockContentSource: ContentSource = {
  async listLocations() {
    return LOCATIONS.map(summaryOf).sort(
      (a, b) => +new Date(b.last_activity_at ?? 0) - +new Date(a.last_activity_at ?? 0),
    );
  },

  async getLocation(locationId: string): Promise<PublicLocationDetail | null> {
    const loc = LOCATIONS.find((l) => l.location_id === locationId);
    if (!loc) return null;
    const observations = [...loc.observations].sort(
      (a, b) => +new Date(b.observed_at) - +new Date(a.observed_at),
    );
    return {
      ...summaryOf(loc),
      conditions: conditionsOf(loc),
      recent_observations: observations,
      photo_count: observations.filter((o) => o.has_photo).length,
      voice_story_count: observations.filter((o) => o.has_audio).length,
      research_summary: loc.research ?? null,
      popular_questions: loc.questions ?? [],
      route: MOCK_ROUTE.stops.some((s) => s.location_id === loc.location_id) ? MOCK_ROUTE : null,
      categories: loc.categories ?? [],
      nearby: nearbyOf(loc),
    };
  },

  async listObservations(params: ListObservationsParams = {}) {
    let items = LOCATIONS.flatMap((l) => l.observations);
    if (params.locationId) {
      const loc = LOCATIONS.find((l) => l.location_id === params.locationId);
      items = loc ? loc.observations : [];
    }
    if (params.knowledgeType) items = items.filter((o) => o.knowledge_type === params.knowledgeType);
    if (params.hasPhoto) items = items.filter((o) => o.has_photo);
    if (params.hasAudio) items = items.filter((o) => o.has_audio);
    items = [...items].sort((a, b) => +new Date(b.observed_at) - +new Date(a.observed_at));
    const total = items.length;
    const offset = params.offset ?? 0;
    const limit = params.limit ?? 25;
    return { items: items.slice(offset, offset + limit), total };
  },

  async getObservation(observationId: string) {
    return LOCATIONS.flatMap((l) => l.observations).find((o) => o.observation_id === observationId) ?? null;
  },

  async listKnowledgeTypes() {
    return KNOWLEDGE_TYPES;
  },

  async search(query: string) {
    const q = query.toLowerCase();
    const locations = LOCATIONS.map(summaryOf).filter(
      (l) => l.name.toLowerCase().includes(q) || (l.description ?? "").toLowerCase().includes(q),
    );
    const observations = LOCATIONS.flatMap((l) => l.observations).filter(
      (o) => (o.evidence ?? "").toLowerCase().includes(q) || o.display_name.toLowerCase().includes(q),
    );
    return { query, locations, observations };
  },
};

/** Which mock location an observation belongs to -- mock data has no
 * location_id on the observation itself (mirrors the real backend, where
 * an Observation only has a raw coordinate, not a Location FK), so this is
 * a demo-only convenience for building "near this place" links in the UI. */
export function findMockLocationForObservation(observationId: string): MockLocation | null {
  return LOCATIONS.find((l) => l.observations.some((o) => o.observation_id === observationId)) ?? null;
}
