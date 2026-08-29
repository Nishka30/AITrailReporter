import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSQLiteContext } from 'expo-sqlite';
import { Ionicons } from '@expo/vector-icons';

import { ApiError, NetworkError } from '../api/client';
import {
  formatApproxValue,
  getGuideRewards,
  getRewardConfig,
  type GuideRewards,
  type RewardConfig,
} from '../api/rewards';
import { AppHeader, Card, EmptyState, ErrorState, Screen, SectionHeader } from '../components/ui';
import { usePullToRefresh } from '../hooks/usePullToRefresh';
import { sumPendingRewardPoints } from '../repositories/answerRepository';
import { colors, radii, shadow, spacing, type } from '../theme/theme';
import type { LocalGuide } from '../types/models';

type Props = {
  guide: LocalGuide;
  onDone: () => void;
};

function describeRule(ruleKey: string, description: string | null): string {
  // The backend's own description is preferred — it comes from the same row
  // the award is paid from, so it can never describe something different from
  // what actually happens. This fallback only fires for a rule added later
  // with no description filled in.
  return description ?? ruleKey.replace(/_/g, ' ');
}

/**
 * Rewards (Step 18).
 *
 * Every number here comes from the backend. The screen holds no point values
 * and no conversion rate of its own, so what it promises can never drift from
 * what is actually awarded, and either can change without an app release.
 *
 * Two totals are shown separately and never added together by this screen:
 * the CONFIRMED balance from the server, and points from answers still waiting
 * to sync. Merging them would imply the server has credited something it
 * hasn't yet.
 */
export default function RewardsScreen({ guide, onDone }: Props) {
  const db = useSQLiteContext();
  const [rewards, setRewards] = useState<GuideRewards | null>(null);
  const [config, setConfig] = useState<RewardConfig | null>(null);
  const [pendingPoints, setPendingPoints] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Local first — this works with no network at all, so the "waiting to
      // sync" figure stays truthful even when the server calls below fail.
      setPendingPoints(await sumPendingRewardPoints(db, guide.id));

      if (!guide.serverGuideId) {
        setRewards(null);
        setConfig(null);
        return;
      }
      const [summary, cfg] = await Promise.all([
        getGuideRewards(guide.serverGuideId),
        getRewardConfig(),
      ]);
      setRewards(summary);
      setConfig(cfg);
    } catch (err) {
      const message =
        err instanceof ApiError || err instanceof NetworkError
          ? err.message
          : 'Could not load your rewards.';
      setError(message);
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [db, guide.id, guide.serverGuideId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const { pulling, onPull } = usePullToRefresh(refresh);

  const conversion = rewards?.conversion ?? config?.conversion ?? null;
  const approxValue =
    rewards && conversion ? formatApproxValue(rewards.currentPoints, conversion) : null;

  return (
    <Screen onRefresh={onPull} refreshing={pulling}>
      <AppHeader title="Rewards" onBack={onDone} />

      {!guide.serverGuideId ? (
        <EmptyState
          icon="cloud-offline-outline"
          title="Sync your profile first"
          message="Your points are tracked on the server. Sync your profile from the Home screen to see them."
        />
      ) : (
        <>
          {/* Balance hero */}
          <View style={styles.hero}>
            <Text style={styles.heroEyebrow}>YOUR POINTS</Text>
            <Text style={styles.heroPoints}>
              {rewards ? rewards.currentPoints.toLocaleString() : loading && !loaded ? '—' : '0'}
            </Text>
            {approxValue ? (
              <Text style={styles.heroValue}>
                ≈ {approxValue} {conversion?.currencyCode}
              </Text>
            ) : null}
            {conversion ? (
              <Text style={styles.heroRate}>
                {conversion.pointsPerCurrencyUnit} points = {conversion.currencySymbol}1.00{' '}
                {conversion.currencyCode}
              </Text>
            ) : null}
          </View>

          {/* Pending points — deliberately its own line, never folded into the
              balance above, because the server has not confirmed these yet. */}
          {pendingPoints > 0 ? (
            <Card variant="flat" style={styles.pendingCard}>
              <View style={styles.pendingRow}>
                <Ionicons name="time-outline" size={17} color={colors.info} />
                <Text style={styles.pendingText}>
                  {pendingPoints} point{pendingPoints === 1 ? '' : 's'} from answers waiting to sync
                </Text>
              </View>
              <Text style={styles.pendingSub}>
                These are added once your answers reach the server. Nothing is lost while you're
                offline.
              </Text>
            </Card>
          ) : null}

          {error ? (
            <View style={styles.errorWrap}>
              <ErrorState message={error} onRetry={refresh} retrying={loading} />
            </View>
          ) : null}

          {/* Contribution stats */}
          {rewards ? (
            <>
              <SectionHeader title="Your contribution" />
              <Card style={styles.statsCard}>
                <View style={styles.statsRow}>
                  {/* Contributions first: it is the broadest, most meaningful
                      number (every note, voice report, discovery and answer),
                      and it is the figure the Profile card links here with. */}
                  <Stat value={rewards.contributionsCount.toLocaleString()} label="Contributions" />
                  <View style={styles.statDivider} />
                  <Stat value={String(rewards.questionsAnswered)} label="Questions answered" />
                  <View style={styles.statDivider} />
                  <Stat value={rewards.totalPointsEarned.toLocaleString()} label="Points all time" />
                </View>
              </Card>
            </>
          ) : null}

          {/* How points are earned — rendered from the SAME rows the backend
              pays from, so this list can never advertise a value that isn't
              actually awarded. */}
          {config && config.rules.length > 0 ? (
            <>
              <SectionHeader title="How you earn points" />
              <Card style={styles.rulesCard}>
                {config.rules.map((rule, i) => (
                  <View
                    key={rule.ruleKey}
                    style={[styles.ruleRow, i > 0 && styles.ruleRowBordered]}
                  >
                    <Text style={styles.ruleText}>{describeRule(rule.ruleKey, rule.description)}</Text>
                    <Text style={styles.rulePoints}>+{rule.points}</Text>
                  </View>
                ))}
              </Card>
            </>
          ) : null}

          {/* Recent activity */}
          {rewards && rewards.recent.length > 0 ? (
            <>
              <SectionHeader title="Recent" />
              <Card style={styles.rulesCard}>
                {rewards.recent.slice(0, 8).map((entry, i) => (
                  <View
                    key={`${entry.awardedAt}-${i}`}
                    style={[styles.ruleRow, i > 0 && styles.ruleRowBordered]}
                  >
                    <Text style={styles.ruleText} numberOfLines={1}>
                      {describeRule(entry.ruleKey, null)}
                    </Text>
                    <Text style={styles.rulePoints}>+{entry.points}</Text>
                  </View>
                ))}
              </Card>
            </>
          ) : null}

          {/* Honest statement of what points currently are. Stated plainly
              rather than implying a payout flow that does not exist. */}
          <Card variant="flat" style={styles.noteCard}>
            <Text style={styles.noteTitle}>About payouts</Text>
            <Text style={styles.noteBody}>
              Points recognise the reports you contribute. There's no way to cash them out in the
              app yet — the value shown above is what they're worth at the current rate, not a
              balance you can withdraw. We'll tell you here when that changes.
            </Text>
          </Card>
        </>
      )}
    </Screen>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: {
    backgroundColor: colors.ink,
    borderRadius: radii.lg,
    padding: spacing.xl,
    marginBottom: spacing.sm,
    ...shadow.card,
  },
  heroEyebrow: { ...type.captionBold, color: colors.marigold, letterSpacing: 0.7 },
  heroPoints: { ...type.display, fontSize: 44, lineHeight: 52, color: colors.white, marginTop: spacing.xxs },
  heroValue: { ...type.title, color: colors.marigoldSoft, marginTop: spacing.xxs },
  heroRate: { ...type.caption, color: 'rgba(255,255,255,0.6)', marginTop: spacing.xs },

  pendingCard: { marginBottom: spacing.sm },
  pendingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  pendingText: { ...type.smallBold, color: colors.info, flexShrink: 1 },
  pendingSub: { ...type.caption, color: colors.inkFaint, marginTop: spacing.xxs, lineHeight: 17 },

  errorWrap: { marginVertical: spacing.sm },

  statsCard: { marginBottom: spacing.sm },
  statsRow: { flexDirection: 'row', alignItems: 'center' },
  stat: { flex: 1, alignItems: 'center' },
  statValue: { ...type.title, color: colors.ink },
  statLabel: { ...type.caption, color: colors.inkFaint, marginTop: 2, textAlign: 'center' },
  statDivider: { width: 1, alignSelf: 'stretch', backgroundColor: colors.border, marginHorizontal: spacing.xs },

  rulesCard: { marginBottom: spacing.sm, paddingVertical: spacing.xxs },
  ruleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
  },
  ruleRowBordered: { borderTopWidth: 1, borderTopColor: colors.border },
  ruleText: { ...type.small, color: colors.inkSoft, flex: 1 },
  rulePoints: { ...type.smallBold, color: colors.marigoldDeep },

  noteCard: { marginTop: spacing.sm, marginBottom: spacing.lg },
  noteTitle: { ...type.smallBold, color: colors.ink },
  noteBody: { ...type.caption, color: colors.inkFaint, marginTop: spacing.xxs, lineHeight: 18 },
});
