/**
 * Runs the REAL demo-data freshness bucketing (mock.ts's
 * bucketMockRouteStopFreshness) against the same boundary cases the backend's
 * _bucket_route_stop_freshness has (test_public_content.py), so mock-mode
 * route-strip statuses stay behaviourally consistent with the real backend.
 * Plain Node via `npx tsx` -- no jest/testing-library, matching this
 * project's actual (zero) existing test infrastructure; mirrors the mobile
 * app's `__xxx_test__.ts` pattern.
 */
import { bucketMockRouteStopFreshness } from "./mock";

let failures = 0;
function check(label: string, cond: boolean, extra: string = ""): void {
  console.log(`[${cond ? "PASS" : "FAIL"}] ${label} ${extra}`);
  if (!cond) failures++;
}

const HOUR = 60 * 60 * 1000;
const hoursAgoIso = (h: number) => new Date(Date.now() - h * HOUR).toISOString();

function run() {
  console.log("=== mock.ts::bucketMockRouteStopFreshness ===");

  const missing = bucketMockRouteStopFreshness(null);
  check("null -> missing, no age", missing.status === "missing" && missing.ageHours === null);

  const atBoundary = bucketMockRouteStopFreshness(hoursAgoIso(72));
  check("exactly at the 72h freshness boundary -> still fresh", atBoundary.status === "fresh", `(got ${atBoundary.status})`);

  const justPastFreshness = bucketMockRouteStopFreshness(hoursAgoIso(72.1));
  check("just past the freshness boundary -> aging", justPastFreshness.status === "aging", `(got ${justPastFreshness.status})`);

  const atAgingBoundary = bucketMockRouteStopFreshness(hoursAgoIso(72 + 96));
  check("exactly at the aging boundary (72+96h) -> still aging", atAgingBoundary.status === "aging", `(got ${atAgingBoundary.status})`);

  const pastAging = bucketMockRouteStopFreshness(hoursAgoIso(72 + 96 + 0.1));
  check("just past the aging boundary -> stale", pastAging.status === "stale", `(got ${pastAging.status})`);

  const fresh = bucketMockRouteStopFreshness(hoursAgoIso(10));
  check("10h ago -> fresh, with a real age_hours", fresh.status === "fresh" && fresh.ageHours !== null && fresh.ageHours > 9.9 && fresh.ageHours < 10.1);

  console.log();
  if (failures > 0) {
    console.log(`FAILURES: ${failures}`);
    process.exit(1);
  }
  console.log("ALL PASSED");
}

run();
