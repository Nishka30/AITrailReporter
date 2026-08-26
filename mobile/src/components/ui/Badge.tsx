import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { colors, radii, spacing, type } from '../../theme/theme';

export type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'brand';

type Props = {
  label: string;
  tone?: BadgeTone;
  icon?: keyof typeof Ionicons.glyphMap;
};

const TONE_STYLES: Record<BadgeTone, { bg: string; fg: string }> = {
  success: { bg: colors.okSoft, fg: colors.ok },
  warning: { bg: colors.marigoldSoft, fg: colors.marigoldDeep },
  danger: { bg: colors.fixSoft, fg: colors.fix },
  info: { bg: colors.infoSoft, fg: colors.info },
  neutral: { bg: colors.neutralSoft, fg: colors.inkSoft },
  brand: { bg: colors.ink, fg: colors.marigoldSoft },
};

/**
 * The single status-communication primitive for the whole app — every
 * sync/transcription/extraction/question/assignment state renders through
 * this, so status always looks and reads consistently (Part J: truthful,
 * translated-to-plain-language, but never conceptually merged).
 */
export default function Badge({ label, tone = 'neutral', icon }: Props) {
  const t = TONE_STYLES[tone];
  return (
    <View style={[styles.base, { backgroundColor: t.bg }]}>
      {icon ? <Ionicons name={icon} size={13} color={t.fg} style={styles.icon} /> : null}
      <Text style={[styles.label, { color: t.fg }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderRadius: radii.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
  },
  icon: { marginRight: 4 },
  label: { ...type.captionBold },
});
