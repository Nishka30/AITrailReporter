/**
 * Presentation-only translation of the backend's knowledge-state vocabulary
 * into plain language. No thresholds, no comparisons, no business logic
 * lives here -- the state itself (fresh/aging/stale/missing) always comes
 * from the backend (app/services/knowledge_state.py /
 * public_content.evaluate_public_knowledge_state), this file only chooses
 * words for it.
 */
import type { KnowledgeState } from "./types";

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

export function freshnessTone(state: KnowledgeState): "good" | "warn" | "bad" | "neutral" {
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
