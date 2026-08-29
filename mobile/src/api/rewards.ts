import { apiRequest } from './client';

/**
 * Rewards (Step 18).
 *
 * THE APP HOLDS NO REWARD AMOUNTS OF ITS OWN. Every point value and the
 * points->money conversion come from the backend, so what the app advertises
 * can never drift from what the backend actually awards, and either can change
 * without an app release. There is no hardcoded number anywhere in the reward
 * UI — where a value is needed offline, it is a value the backend previously
 * sent and the device stored (see LocalAnswer.rewardPoints).
 */

export interface RewardConversion {
  pointsPerCurrencyUnit: number;
  currencyCode: string;
  currencySymbol: string;
}

export interface RewardRule {
  ruleKey: string;
  points: number;
  description: string | null;
}

export interface RewardConfig {
  rules: RewardRule[];
  conversion: RewardConversion;
}

export interface RewardLedgerEntry {
  points: number;
  ruleKey: string;
  sourceType: string;
  awardedAt: string;
}

export interface GuideRewards {
  guideId: string;
  /** Equal to totalPointsEarned until a redemption mechanism exists. */
  currentPoints: number;
  totalPointsEarned: number;
  totalAwards: number;
  questionsAnswered: number;
  /** Everything the guide has actually contributed — notes, voice reports,
   * Explore discoveries and answers. Counted from real submissions, so a
   * contribution made before rewards existed still counts. */
  contributionsCount: number;
  conversion: RewardConversion;
  recent: RewardLedgerEntry[];
}

interface ConversionWire {
  points_per_currency_unit: number;
  currency_code: string;
  currency_symbol: string;
}

interface RewardConfigWire {
  rules: { rule_key: string; points: number; description: string | null }[];
  conversion: ConversionWire;
}

interface GuideRewardsWire {
  guide_id: string;
  current_points: number;
  total_points_earned: number;
  total_awards: number;
  questions_answered: number;
  contributions_count: number;
  conversion: ConversionWire;
  recent: { points: number; rule_key: string; source_type: string; awarded_at: string }[];
}

function conversionFromWire(w: ConversionWire): RewardConversion {
  return {
    pointsPerCurrencyUnit: w.points_per_currency_unit,
    currencyCode: w.currency_code,
    currencySymbol: w.currency_symbol,
  };
}

/** GET /api/v1/rewards/config — every active earning rule plus the
 * conversion. Used to label Explore prompt cards and to render the Rewards
 * screen's "how you earn" list from the same rows the backend pays from. */
export async function getRewardConfig(): Promise<RewardConfig> {
  const wire = await apiRequest<RewardConfigWire>('/api/v1/rewards/config');
  return {
    rules: wire.rules.map((r) => ({
      ruleKey: r.rule_key,
      points: r.points,
      description: r.description,
    })),
    conversion: conversionFromWire(wire.conversion),
  };
}

/** GET /api/v1/guides/{guideId}/rewards — the AUTHORITATIVE totals. Whatever
 * this returns supersedes any provisional total the device computed while
 * offline; the app must never add its own pending points on top of these. */
export async function getGuideRewards(guideId: string): Promise<GuideRewards> {
  const wire = await apiRequest<GuideRewardsWire>(`/api/v1/guides/${guideId}/rewards`);
  return {
    guideId: wire.guide_id,
    currentPoints: wire.current_points,
    totalPointsEarned: wire.total_points_earned,
    totalAwards: wire.total_awards,
    questionsAnswered: wire.questions_answered,
    // `?? 0` so a backend predating this field degrades to a truthful zero
    // rather than rendering `undefined` in the Profile card.
    contributionsCount: wire.contributions_count ?? 0,
    conversion: conversionFromWire(wire.conversion),
    recent: wire.recent.map((e) => ({
      points: e.points,
      ruleKey: e.rule_key,
      sourceType: e.source_type,
      awardedAt: e.awarded_at,
    })),
  };
}

/** Formats a point total as its approximate money value using the BACKEND's
 * conversion. Returns null when the conversion is unusable, so the UI can omit
 * the line entirely rather than print a misleading "$0.00" or "$NaN". */
export function formatApproxValue(points: number, conversion: RewardConversion): string | null {
  if (!conversion.pointsPerCurrencyUnit || conversion.pointsPerCurrencyUnit <= 0) return null;
  const value = points / conversion.pointsPerCurrencyUnit;
  return `${conversion.currencySymbol}${value.toFixed(2)}`;
}
