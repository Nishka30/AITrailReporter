/**
 * Deterministic, non-LLM matching between a free-text question and the REAL
 * data already loaded for a place (its knowledge-type conditions and
 * approved observations' evidence text). No generation happens here --
 * this only scores and ranks existing content, so it can never answer with
 * something the data doesn't actually say. See components/AskAboutPlace.tsx.
 */
import type { PublicConditionState, PublicObservation } from "./types";

const STOPWORDS = new Set([
  "is","are","was","were","the","a","an","to","of","in","on","at","it","its","there","right",
  "now","how","hows","what","whats","any","about","near","here","today","currently","still",
  "and","or","for","do","does","did","been","being","be","this","that","with","recent","recently",
  // Generic pronouns/adverbs -- deliberately stopped rather than tokenized:
  // short substrings of these ("where" inside "somewhere", "thing" inside
  // "anything") were producing false-positive matches against unrelated
  // words that happen to contain them.
  "where","somewhere","anywhere","everywhere","something","anything","everything","nothing",
  "when","who","which","can","could","would","will","does","doing",
]);

// Small, hand-written synonym groups for the vocabulary travellers actually
// use vs. the more clinical knowledge-type display names. Purely additive --
// an unknown/future knowledge type (dynamic types, per KnowledgeTypeConfig)
// still matches fine via plain word overlap against its own display_name,
// this just improves recall for the common seeded categories.
const SYNONYM_GROUPS: string[][] = [
  ["weather", "rain", "raining", "temperature", "cold", "hot", "sunny", "sun", "wind", "windy", "clear"],
  ["snow", "ice", "icy", "frozen", "frost", "packed"],
  ["trail", "path", "track", "route", "walk", "walking", "hike", "hiking", "surface"],
  ["obstruction", "block", "blocked", "blockage", "landslide", "rockslide", "closed", "closure", "debris", "road"],
  ["signal", "network", "coverage", "mobile", "phone", "wifi", "data", "reception"],
  ["park", "parking", "car", "vehicle", "taxi", "space"],
  ["water", "drink", "drinking", "tap", "spring", "potable"],
];

// Exported so globalAsk.ts's cross-place fallback can rank against the same
// vocabulary/synonyms rather than re-implementing (or worse, diverging
// from) this matching logic.
export function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((w) => w.length >= 3 && !STOPWORDS.has(w));
}

export function expandTokens(tokens: string[]): Set<string> {
  const expanded = new Set(tokens);
  for (const token of tokens) {
    for (const group of SYNONYM_GROUPS) {
      if (group.some((w) => w.includes(token) || token.includes(w))) {
        group.forEach((w) => expanded.add(w));
      }
    }
  }
  return expanded;
}

export function scoreText(candidateText: string, queryTokens: Set<string>): number {
  const candidateTokens = tokenize(candidateText);
  let matches = 0;
  for (const c of candidateTokens) {
    for (const q of queryTokens) {
      if (c === q || c.includes(q) || q.includes(c)) {
        matches += 1;
        break;
      }
    }
  }
  return matches;
}

export function valueText(value: Record<string, unknown>): string {
  return Object.values(value)
    .filter((v) => typeof v === "string" || typeof v === "number" || typeof v === "boolean")
    .map(String)
    .join(" ");
}

export interface AskResult {
  matchedCondition: PublicConditionState | null;
  groundingObservation: PublicObservation | null;
  supportingObservations: PublicObservation[];
}

export function askAboutPlace(
  question: string,
  conditions: PublicConditionState[],
  observations: PublicObservation[],
): AskResult {
  const queryTokens = expandTokens(tokenize(question));
  if (queryTokens.size === 0) {
    return { matchedCondition: null, groundingObservation: null, supportingObservations: [] };
  }

  const rankedConditions = conditions
    .map((c) => ({ c, s: scoreText(`${c.display_name} ${c.knowledge_type}`, queryTokens) }))
    .filter((r) => r.s > 0)
    .sort((a, b) => b.s - a.s);

  const rankedObservations = observations
    .map((o) => ({ o, s: scoreText(`${o.display_name} ${o.evidence ?? ""} ${valueText(o.value)}`, queryTokens) }))
    .filter((r) => r.s > 0)
    .sort((a, b) => b.s - a.s);

  const matchedCondition = rankedConditions[0]?.c ?? null;
  const groundingObservation = matchedCondition
    ? observations.find((o) => o.observation_id === matchedCondition.latest_observation_id) ?? null
    : null;

  const supportingObservations = rankedObservations
    .map((r) => r.o)
    .filter((o) => o.observation_id !== groundingObservation?.observation_id)
    .slice(0, 3);

  return { matchedCondition, groundingObservation, supportingObservations };
}
