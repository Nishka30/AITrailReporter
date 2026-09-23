/**
 * Runs the REAL mobile TypeScript (not a reimplementation) against the
 * Location Picker's category-grouping logic in
 * src/screens/placeCandidateGrouping.ts. Same plain-tsx pattern as
 * __location_test__.ts; this module has no React Native import so it needs
 * no loader hook.
 */
import type { PlaceCandidate } from './src/api/placeCandidates';
import { groupByCategory, UNCATEGORIZED_LABEL } from './src/screens/placeCandidateGrouping';

let failures = 0;
function check(label: string, cond: boolean, extra: string = ''): void {
  console.log(`[${cond ? 'PASS' : 'FAIL'}] ${label} ${extra}`);
  if (!cond) failures++;
}

let nextId = 0;
function candidate(name: string, category: string | null, overrides: Partial<PlaceCandidate> = {}): PlaceCandidate {
  nextId += 1;
  return {
    id: `id-${nextId}`,
    name,
    distanceMeters: 0,
    latitude: 12.9716,
    longitude: 77.5946,
    category,
    subcategory: null,
    placeKind: null,
    externalPlaceId: null,
    provider: 'google',
    formattedAddress: null,
    isArea: false,
    ...overrides,
  };
}

function run() {
  console.log('=== placeCandidateGrouping.ts::groupByCategory ===');

  // Backend already interleaves by round-robin, so the input order here is
  // deliberately "already ranked" -- grouping must not re-sort it.
  const restaurantA = candidate('Restaurant A', 'Food & Drink');
  const park = candidate('Green Park', 'Nature');
  const restaurantB = candidate('Restaurant B', 'Food & Drink');
  const temple = candidate('Shiva Temple', 'Culture & Heritage');

  const groups = groupByCategory([restaurantA, park, restaurantB, temple]);
  check('produces one group per distinct category', groups.length === 3, `(got ${groups.length})`);
  check(
    'group order is first-appearance order, not alphabetical/re-sorted',
    groups.map((g) => g.key).join(',') === 'Food & Drink,Nature,Culture & Heritage',
    `(got ${groups.map((g) => g.key).join(',')})`
  );
  const foodGroup = groups.find((g) => g.key === 'Food & Drink')!;
  check(
    'within-group order is preserved exactly as received',
    foodGroup.candidates.map((c) => c.name).join(',') === 'Restaurant A,Restaurant B'
  );
  check('empty categories never appear', groups.every((g) => g.candidates.length > 0));

  // Single category -- exactly what "only restaurants nearby" looks like.
  const singleCategory = groupByCategory([restaurantA, restaurantB]);
  check(
    'a single category yields exactly one group, not split further',
    singleCategory.length === 1 && singleCategory[0].candidates.length === 2
  );

  // No candidates at all.
  check('an empty candidate list yields no groups', groupByCategory([]).length === 0);

  // Unclassified candidates get their own labelled group, never dropped or
  // silently merged into a real category.
  const mystery = candidate('Mystery Spot', null);
  const withUnclassified = groupByCategory([restaurantA, mystery]);
  check(
    'an unclassified candidate becomes its own group under UNCATEGORIZED_LABEL',
    withUnclassified.some((g) => g.key === UNCATEGORIZED_LABEL && g.candidates[0].name === 'Mystery Spot')
  );

  // Two unclassified candidates land in the SAME group, not two.
  const mystery2 = candidate('Mystery Spot 2', null);
  const twoUnclassified = groupByCategory([mystery, mystery2]);
  check(
    'multiple unclassified candidates share one group',
    twoUnclassified.length === 1 && twoUnclassified[0].candidates.length === 2
  );

  // Grouping never mutates the input array or its elements.
  const original = [restaurantA, park];
  const originalCopy = [...original];
  groupByCategory(original);
  check(
    'grouping does not mutate the input array',
    JSON.stringify(original) === JSON.stringify(originalCopy)
  );

  console.log();
  if (failures > 0) {
    console.log(`FAILURES: ${failures}`);
    process.exit(1);
  }
  console.log('ALL PASSED');
}

run();
