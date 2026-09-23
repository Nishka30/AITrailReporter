import type { PlaceCandidate } from '../api/placeCandidates';

/**
 * Groups the Location Picker's (non-area) candidates by category for display
 * -- pulled out of PlacePickerScreen.tsx as a plain function, with no
 * React Native import, so it can be exercised directly under plain Node/tsx
 * the same way coordinateValidation.ts and photoLocationResolver.ts are
 * (see __location_test__.ts).
 */

/** Label for candidates with no TrailMind category (pre-classification rows,
 * or a type Google returned that nothing in the taxonomy maps to yet). Never
 * invented per-place -- same "Other" the backend already uses. */
export const UNCATEGORIZED_LABEL = 'Other nearby places';

export type CandidateGroup = { key: string; label: string; candidates: PlaceCandidate[] };

/**
 * Buckets the (non-area) candidates by `category` -- the SAME field the
 * backend's round-robin ranking (place_candidates.py::_rank) diversifies by,
 * so a group here always matches a "turn" the ranking gave that category.
 *
 * Group order is first-appearance order in the already-ranked list, which is
 * exactly the backend's "closest available category goes first" order --
 * this never re-sorts, it only labels what ranking already decided. Order
 * WITHIN a group is untouched for the same reason: the backend already
 * sorted same-category candidates by distance/quality before interleaving.
 */
export function groupByCategory(candidates: PlaceCandidate[]): CandidateGroup[] {
  const order: string[] = [];
  const byKey = new Map<string, PlaceCandidate[]>();
  for (const candidate of candidates) {
    const key = candidate.category ?? UNCATEGORIZED_LABEL;
    if (!byKey.has(key)) {
      byKey.set(key, []);
      order.push(key);
    }
    byKey.get(key)!.push(candidate);
  }
  return order.map((key) => ({ key, label: key, candidates: byKey.get(key)! }));
}
