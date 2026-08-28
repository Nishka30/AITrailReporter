/**
 * Global version of ask.ts: the question doesn't name a place page it's
 * already on, so we first try to work out WHICH place it's about from the
 * text itself, then reuse the exact same deterministic, non-LLM matching.
 * If no place is named (or nothing matches), falls back to the existing
 * deterministic public search (content.search) -- still 100% real data,
 * never generated. See components/AskAnything.tsx.
 */
import { content } from "./index";
import { askAboutPlace, expandTokens, scoreText, tokenize, valueText } from "./ask";
import type { PublicConditionState, PublicLocationSummary, PublicObservation } from "./types";

const GLOBAL_FALLBACK_POOL_SIZE = 150;

function normalizeWords(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

/** Finds the most specific known place named in the question -- requires
 * every significant (3+ letter) word of a place's name to appear in the
 * question, then prefers the longest such match, so "Leh" doesn't win over
 * "Khardung La" just because it matches first. */
export function detectPlace(question: string, locations: PublicLocationSummary[]): PublicLocationSummary | null {
  const questionWords = new Set(normalizeWords(question));
  let best: { location: PublicLocationSummary; specificity: number } | null = null;

  for (const location of locations) {
    const nameWords = normalizeWords(location.name).filter((w) => w.length >= 3);
    if (nameWords.length === 0) continue;
    const allPresent = nameWords.every((w) => questionWords.has(w));
    if (!allPresent) continue;
    const specificity = nameWords.join("").length;
    if (!best || specificity > best.specificity) {
      best = { location, specificity };
    }
  }
  return best?.location ?? null;
}

export interface GlobalAskResult {
  place: PublicLocationSummary | null;
  matchedCondition: PublicConditionState | null;
  groundingObservation: PublicObservation | null;
  supportingObservations: PublicObservation[];
  fallbackObservations: PublicObservation[];
  fallbackPlaces: PublicLocationSummary[];
}

export async function askAnything(question: string, locations: PublicLocationSummary[]): Promise<GlobalAskResult> {
  const place = detectPlace(question, locations);

  if (place) {
    const detail = await content.getLocation(place.location_id);
    if (detail) {
      const result = askAboutPlace(question, detail.conditions, detail.recent_observations);
      if (result.matchedCondition) {
        return {
          place,
          matchedCondition: result.matchedCondition,
          groundingObservation: result.groundingObservation,
          supportingObservations: result.supportingObservations,
          fallbackObservations: [],
          fallbackPlaces: [],
        };
      }
    }
  }

  // No place named, or that place had nothing matching this question --
  // fall back to the SAME token/synonym scoring ask.ts uses for a single
  // place, just run across every recent observation and place. (Not
  // content.search(): that does whole-phrase substring matching, tuned for
  // short keyword queries on /search, not full natural-language questions
  // -- "any parking near the lake?" would rarely appear verbatim in any
  // evidence text.)
  const queryTokens = expandTokens(tokenize(question));
  if (queryTokens.size === 0) {
    return { place: null, matchedCondition: null, groundingObservation: null, supportingObservations: [], fallbackObservations: [], fallbackPlaces: [] };
  }

  const pool = await content.listObservations({ limit: GLOBAL_FALLBACK_POOL_SIZE });
  const fallbackObservations = pool.items
    .map((o) => ({ o, s: scoreText(`${o.display_name} ${o.evidence ?? ""} ${valueText(o.value)}`, queryTokens) }))
    .filter((r) => r.s > 0)
    .sort((a, b) => b.s - a.s)
    .map((r) => r.o)
    .slice(0, 4);

  const fallbackPlaces = locations
    .map((l) => ({ l, s: scoreText(`${l.name} ${l.description ?? ""}`, queryTokens) }))
    .filter((r) => r.s > 0)
    .sort((a, b) => b.s - a.s)
    .map((r) => r.l)
    .slice(0, 3);

  return {
    place: null,
    matchedCondition: null,
    groundingObservation: null,
    supportingObservations: [],
    fallbackObservations,
    fallbackPlaces,
  };
}
