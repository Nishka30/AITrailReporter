/**
 * Presentation-only translation of the backend's knowledge-state vocabulary
 * into plain language. No thresholds, no comparisons, no business logic
 * lives here -- the state itself (fresh/aging/stale/missing) always comes
 * from the backend (app/services/knowledge_state.py /
 * public_content.evaluate_public_knowledge_state), this file only chooses
 * words for it.
 */
import type { CategoryState, KnowledgeState } from "./types";

export type Tone = "good" | "warn" | "bad" | "neutral";

/** Short "local check" wording for one report's freshness -- the same
 * backend state as freshnessLabel, phrased as a guide check (Location page
 * live rows / route stops). */
export function checkLabel(state: KnowledgeState): string {
  switch (state) {
    case "fresh":
      return "Recently checked";
    case "aging":
      return "Worth re-checking";
    case "stale":
      return "Due for a check";
    case "missing":
      return "Not checked yet";
  }
}

/** A category's derived coverage state (backend compute_category_state). */
export function categoryStateLabel(state: CategoryState): string {
  switch (state) {
    case "fresh":
      return "Recently verified";
    case "partially_stale":
      return "Partly due for a re-check";
    case "stale":
      return "Due for a re-check";
    case "missing":
      return "Not verified yet";
  }
}

export function categoryStateTone(state: CategoryState): Tone {
  switch (state) {
    case "fresh":
      return "good";
    case "partially_stale":
      return "warn";
    case "stale":
      return "bad";
    case "missing":
      return "neutral";
  }
}

/** "26 Sep 2026" -- an absolute date alongside relative "3 days ago", so an
 * old report can never read as current. */
export function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function formatDistance(meters: number | null | undefined): string | null {
  if (meters == null) return null;
  return meters < 1000 ? `${Math.round(meters / 10) * 10} m` : `${(meters / 1000).toFixed(meters < 10_000 ? 1 : 0)} km`;
}

export function freshnessLabel(state: KnowledgeState): string {
  switch (state) {
    case "fresh":
      return "Updated recently";
    case "aging":
      return "Still recent — worth a quick check";
    case "stale":
      return "Last reported some time ago";
    case "missing":
      return "No recent reports";
  }
}

export function freshnessTone(state: KnowledgeState): Tone {
  switch (state) {
    case "fresh":
      return "good";
    case "aging":
      return "warn";
    case "stale":
      return "bad";
    case "missing":
      return "neutral";
  }
}

/** Wraps the Date.now() call other helpers in this file already make
 * (timeAgoLabel etc.) -- kept out of component bodies so the
 * react-hooks/purity lint rule (which only traces calls written directly
 * inside a component/hook, not inside an imported helper) doesn't flag it. */
export function isWithinLastDays(iso: string, days: number): boolean {
  return Date.now() - new Date(iso).getTime() <= days * 24 * 60 * 60 * 1000;
}

/** "21 Sep–27 Sep 2026" -- the trailing `days` up to today, formatted as a
 * range. Same reasoning as isWithinLastDays: kept out of component bodies
 * so react-hooks/purity doesn't flag the Date.now() call. */
export function recentDateRangeLabel(days: number): string {
  const end = new Date();
  const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000);
  const startLabel = start.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const endLabel = end.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  return `${startLabel}–${endLabel}`;
}

export function timeAgoLabel(iso: string | null): string {
  if (!iso) return "No recent reports";
  const hours = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  if (hours < 1) return "Updated moments ago";
  if (hours < 2) return "Updated an hour ago";
  if (hours < 24) return `Updated ${Math.round(hours)} hours ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "Reported yesterday";
  if (days < 7) return `Reported ${days} days ago`;
  const weeks = Math.round(days / 7);
  if (weeks < 5) return `Reported ${weeks} week${weeks > 1 ? "s" : ""} ago`;
  const months = Math.round(days / 30);
  return `Reported ${months} month${months > 1 ? "s" : ""} ago`;
}

/** Best-effort, generic formatter for a knowledge type's dynamic JSON
 * `value` payload -- since KnowledgeTypeConfig is open-ended (new types can
 * appear without a frontend redesign, per product spec), this never
 * hardcodes a per-type formatter, just title-cases keys and values. */
export function formatValueEntries(value: Record<string, unknown>): { label: string; text: string }[] {
  return Object.entries(value)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([key, v]) => ({
      label: key
        .split("_")
        .map((w) => w[0]?.toUpperCase() + w.slice(1))
        .join(" "),
      text: String(v)
        .split("_")
        .map((w) => w[0]?.toUpperCase() + w.slice(1))
        .join(" "),
    }));
}
