/**
 * Presentation shaping for the editorial guide pages. Never invents
 * content: it only drops text that must not reach travellers (placeholder
 * descriptions, internal notes) and reformats research prose for reading.
 */
import type { PublicLocationSummary, PublicResearchFinding, PublicRoute } from "./types";

/** "A hotel near here." / "A sublocality level 1 near here." are generated
 * placeholders, not descriptions. Sentences addressed to the app's own
 * builders ("It can help the app test ...") are internal notes. */
export function cleanDescription(text: string | null | undefined): string | null {
  if (!text) return null;
  if (/^an? [\w\s-]{1,40} near here\.?$/i.test(text.trim())) return null;
  const sentences = text.match(/[^.!?]+[.!?]+(\s|$)/g) ?? [text];
  const kept = sentences.filter(
    (s) => !/\bthe app\b|\bapp test|\btest(s|ing)? (the|whether)\b|\btrial\b|\bpilot\b|himalayan wonders|\bmapped\b|comparing it with|\bseed(ed)? data\b/i.test(s),
  );
  // Dropping part of a description leaves dangling references ("It is
  // useful for..."), so any internal note voids the whole description.
  if (kept.length !== sentences.length) return null;
  const result = kept.join("").trim();
  return result.length > 0 ? result : null;
}

export type ResearchBlock = { kind: "p"; text: string } | { kind: "list"; heading: string | null; items: string[] };

const META = /(do(es)? not|don['’]t|doesn['’]t) (clearly |specifically )?(say|mention|give|state|establish)|say(s)? (only )?(a )?little|mostly say only|not clearly reliable|^there (are|is) n|results (say|mostly)|beyond (that|the naming)|not (a )?clearly|is not clear/i;

function stripCitations(text: string): string {
  return text
    .replace(/\s?(\[\d+\])+/g, "")
    .replace(/\s+([.,;:])/g, "$1")
    .replace(/�/g, "–")
    .trim();
}

/** A finding's condensed web summary as readable blocks: citation markers
 * removed, meta-commentary about what sources *didn't* say dropped, and a
 * final sentence cut off by the storage cap trimmed. */
export function researchBlocks(summary: string): ResearchBlock[] {
  const lines = summary
    .split(/\n+/)
    .map((l) => stripCitations(l))
    .filter(Boolean);
  const blocks: ResearchBlock[] = [];
  let list: { kind: "list"; heading: string | null; items: string[] } | null = null;
  let skipList = false;

  for (const line of lines) {
    if (/^[-*•]\s+/.test(line)) {
      const item = line.replace(/^[-*•]\s+/, "");
      if (skipList || META.test(item)) continue;
      if (!list) {
        list = { kind: "list", heading: null, items: [] };
        blocks.push(list);
      }
      list.items.push(item);
      continue;
    }
    list = null;
    if (line.endsWith(":")) {
      skipList = META.test(line) || /do not|don['’]t/i.test(line);
      if (!skipList) {
        list = { kind: "list", heading: line.replace(/:$/, ""), items: [] };
        blocks.push(list);
      }
      continue;
    }
    skipList = false;
    if (META.test(line)) continue;
    blocks.push({ kind: "p", text: line });
  }

  const cleaned = blocks.filter((b) => b.kind === "p" || b.items.length > 0);
  const last = cleaned[cleaned.length - 1];
  if (last?.kind === "p" && !/[.!?)"”]$/.test(last.text)) {
    const cut = last.text.replace(/[^.!?]*$/, "").trim();
    if (cut) last.text = cut;
    else cleaned.pop();
  } else if (last?.kind === "list") {
    const tail = last.items[last.items.length - 1];
    if (tail && !/[.!?)"”]$/.test(tail)) last.items.pop();
  }
  return cleaned;
}

export function findingQuestion(f: PublicResearchFinding): string {
  return f.topic === "current"
    ? `What do sources say is currently true about ${f.location_name}?`
    : `What do visitors notice about ${f.location_name}?`;
}

export function shortTitle(title: string | null, url: string, max = 70): string {
  const t = (title ?? "").trim() || hostnameOf(url);
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t;
}

export function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function placeTypeOf(place: PublicLocationSummary): string | null {
  return place.categories?.find((c) => c.kind === "place_type")?.display_name ?? null;
}

export function themesOf(place: PublicLocationSummary): { slug: string; display_name: string }[] {
  return (place.categories ?? []).filter((c) => c.kind === "theme");
}

export interface PlaceGroup {
  key: string;
  label: string;
  places: PublicLocationSummary[];
}

/** Nearby places grouped by the themes they actually share (a theme needs
 * >= 2 places to become a group), most common first; each place joins the
 * first of its themes that is a group. Places with none go to "More nearby". */
export function groupPlaces(places: PublicLocationSummary[], maxGroups = 4): PlaceGroup[] {
  const label = new Map<string, string>();
  const firstCounts = new Map<string, number>();
  for (const p of places) {
    const themes = themesOf(p);
    for (const t of themes) label.set(t.slug, t.display_name);
    if (themes[0]) firstCounts.set(themes[0].slug, (firstCounts.get(themes[0].slug) ?? 0) + 1);
  }
  // A place joins its MOST relevant theme when that theme is shared; else
  // the next of its themes that other places lead with.
  const leading = new Set([...firstCounts.entries()].filter(([, n]) => n >= 2).map(([slug]) => slug));
  const assigned = new Map<string, PublicLocationSummary[]>();
  const rest: PublicLocationSummary[] = [];
  for (const p of places) {
    const slug = themesOf(p).find((t) => leading.has(t.slug))?.slug;
    if (slug) assigned.set(slug, [...(assigned.get(slug) ?? []), p]);
    else rest.push(p);
  }
  const ordered = [...assigned.entries()].sort((a, b) => b[1].length - a[1].length || label.get(a[0])!.localeCompare(label.get(b[0])!));
  for (const [, ps] of ordered.slice(maxGroups)) rest.push(...ps);
  return [
    ...ordered.slice(0, maxGroups).map(([slug, ps]) => ({ key: slug, label: label.get(slug)!, places: ps })),
    ...(rest.length ? [{ key: "more", label: "More nearby", places: rest }] : []),
  ];
}

export function routeNeighbours(route: PublicRoute, locationId: string) {
  const stops = [...route.stops].sort((a, b) => a.sequence_order - b.sequence_order);
  const i = stops.findIndex((s) => s.location_id === locationId);
  return { stops, index: i, previous: i > 0 ? stops[i - 1] : null, current: i >= 0 ? stops[i] : null, next: i >= 0 && i < stops.length - 1 ? stops[i + 1] : null };
}

export function formatMeters(m: number | null | undefined): string | null {
  if (m == null) return null;
  return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(m < 10_000 ? 1 : 0)} km`;
}

/** "27 Sep 2026 · 15:40" -- absolute, so an old report never reads as current. */
export function dateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })} · ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
}

/** Kept out of component bodies (react-hooks/purity). */
export function nowMs(): number {
  return Date.now();
}
