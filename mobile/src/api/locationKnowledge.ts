import { apiRequest } from './client';

/**
 * PRIMARY (category-driven) knowledge coverage for one Location —
 * GET /api/v1/locations/{id}/knowledge-status.
 *
 * Read-only, never triggers generation or research. Used to ground Explore
 * prompts around real missing/stale categories (see
 * explore/explorePrompts.ts) — the backend remains the single source of
 * truth for coverage/freshness/volatility; this app only ever displays it.
 */

/** One of 'missing' / 'fresh' / 'stale' / 'partially_stale'. */
export type CategoryCoverageState = 'missing' | 'fresh' | 'stale' | 'partially_stale';

export interface CategoryCoverage {
  categoryAssignmentId: string;
  kind: string;
  slug: string;
  displayName: string;
  relevance: number;
  isPrimary: boolean;
  state: CategoryCoverageState;
}

export interface LocationKnowledgeStatus {
  locationId: string;
  locationName: string;
  categories: CategoryCoverage[];
}

interface CategoryCoverageWire {
  category_assignment_id: string;
  kind: string;
  slug: string;
  display_name: string;
  relevance: number;
  is_primary: boolean;
  state: CategoryCoverageState;
}

interface LocationKnowledgeStatusWire {
  location_id: string;
  location_name: string;
  categories: CategoryCoverageWire[];
}

export async function getLocationKnowledgeStatus(
  locationId: string
): Promise<LocationKnowledgeStatus> {
  const wire = await apiRequest<LocationKnowledgeStatusWire>(
    `/api/v1/locations/${locationId}/knowledge-status`
  );
  return {
    locationId: wire.location_id,
    locationName: wire.location_name,
    categories: wire.categories.map((c) => ({
      categoryAssignmentId: c.category_assignment_id,
      kind: c.kind,
      slug: c.slug,
      displayName: c.display_name,
      relevance: c.relevance,
      isPrimary: c.is_primary,
      state: c.state,
    })),
  };
}

/** Only the categories worth grounding a prompt around — mirrors how
 * buildPrompts already filters knowledgeStates down to non-fresh gaps. */
export function coverageGaps(status: LocationKnowledgeStatus | null): CategoryCoverage[] {
  if (!status) return [];
  return status.categories.filter((c) => c.state !== 'fresh');
}
