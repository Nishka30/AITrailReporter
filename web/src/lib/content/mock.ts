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
  ContentSource,
  ListObservationsParams,
  PublicConditionState,
  PublicKnowledgeType,
  PublicLocationDetail,
  PublicLocationSummary,
  PublicObservation,
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
    photo_url: input.photoSeed ? `https://picsum.photos/seed/${input.photoSeed}/1600/1000` : null,
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
}

const LOCATIONS: MockLocation[] = [
  {
    location_id: "leh",
    name: "Leh",
    description:
      "The high-desert gateway to Ladakh, 3,500m up -- monasteries, market lanes, and the last reliable mobile signal before the passes.",
    latitude: 34.1526,
    longitude: 77.5771,
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
