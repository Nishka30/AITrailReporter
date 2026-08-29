import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { colors, radii, spacing, type } from '../../theme/theme';

type Props = {
  points: number;
  /** 'quiet' (default) for cards, where the reward is a supporting detail;
   * 'strong' for the one place a reward is the subject (the answer screen's
   * confirmation), never for lists. */
  variant?: 'quiet' | 'strong';
  /** Marks points earned but not yet confirmed by the server. */
  pending?: boolean;
};

/**
 * The single reward-display primitive (Step 18) — every "+N points" in the app
 * renders through this, exactly as every status renders through Badge.
 *
 * DELIBERATELY UNDERSTATED. The product rule is that rewards motivate without
 * intruding: the reason to answer is that the next traveller needs to know. So
 * this has no animation, no gradient, no celebration, and is never the largest
 * or brightest element on a card. It reads as a quiet fact about the task, not
 * a prize — which is also why there is no "streak", "multiplier" or
 * progress-bar variant here.
 *
 * `points` always comes from the backend (see api/rewards.ts). This component
 * never computes or defaults a value; a caller with no server-issued number
 * should render nothing at all rather than guess one.
 */
export default function RewardChip({ points, variant = 'quiet', pending = false }: Props) {
  const strong = variant === 'strong';
  return (
    <View style={[styles.base, strong ? styles.strong : styles.quiet]}>
      <Ionicons
        name={pending ? 'time-outline' : 'add-circle-outline'}
        size={strong ? 15 : 13}
        color={strong ? colors.marigoldSoft : colors.marigoldDeep}
      />
      <Text
        style={[styles.label, strong ? styles.labelStrong : styles.labelQuiet]}
        numberOfLines={1}
      >
        {points} {points === 1 ? 'point' : 'points'}
        {pending ? ' pending' : ''}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 4,
    borderRadius: radii.pill,
    paddingHorizontal: spacing.xs,
    paddingVertical: 4,
  },
  quiet: { backgroundColor: colors.marigoldSoft },
  strong: { backgroundColor: colors.ink, paddingHorizontal: spacing.sm, paddingVertical: 6 },
  label: { ...type.captionBold },
  labelQuiet: { color: colors.marigoldDeep },
  labelStrong: { color: colors.marigoldSoft },
});
