import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing, type } from '../../theme/theme';

type Props = {
  title: string;
  /** e.g. a count like "3" — rendered as muted trailing text. */
  meta?: string;
  right?: React.ReactNode;
};

/** Small caps-style label above a group of cards/rows. */
export default function SectionHeader({ title, meta, right }: Props) {
  return (
    <View style={styles.row}>
      <Text style={styles.title}>
        {title}
        {meta ? <Text style={styles.meta}> · {meta}</Text> : null}
      </Text>
      {right}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  title: { ...type.captionBold, color: colors.inkSoft, letterSpacing: 0.6, textTransform: 'uppercase' },
  meta: { ...type.caption, color: colors.inkFaint, textTransform: 'none' },
});
