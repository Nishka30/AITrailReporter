import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { colors, minTouchSize, spacing, type } from '../../theme/theme';

type Props = {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  /** Right-side slot, e.g. a small action button. */
  right?: React.ReactNode;
};

/**
 * Consistent header for every non-tab (pushed) screen — back chevron, title,
 * optional subtitle, optional right-side action. Tab-root screens
 * (Home/Questions/Activity) use their own bigger hero header instead (see
 * HomeScreen.tsx) since they don't need a back button.
 */
export default function AppHeader({ title, subtitle, onBack, right }: Props) {
  return (
    <View style={styles.container}>
      <View style={styles.row}>
        {onBack ? (
          <Pressable
            onPress={onBack}
            hitSlop={12}
            style={styles.backButton}
            accessibilityRole="button"
            accessibilityLabel="Go back"
          >
            <Ionicons name="chevron-back" size={22} color={colors.ink} />
          </Pressable>
        ) : (
          <View style={styles.backButtonPlaceholder} />
        )}
        <View style={styles.titleWrap}>
          <Text style={styles.title} numberOfLines={2}>
            {title}
          </Text>
          {subtitle ? (
            <Text style={styles.subtitle} numberOfLines={2}>
              {subtitle}
            </Text>
          ) : null}
        </View>
        <View style={styles.rightSlot}>{right}</View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginBottom: spacing.lg },
  row: { flexDirection: 'row', alignItems: 'flex-start' },
  backButton: {
    width: minTouchSize,
    height: minTouchSize,
    marginLeft: -spacing.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  backButtonPlaceholder: { width: spacing.xs },
  titleWrap: { flex: 1, paddingTop: spacing.xs },
  title: { ...type.title, color: colors.ink },
  subtitle: { ...type.small, color: colors.inkFaint, marginTop: 2 },
  rightSlot: { minWidth: spacing.xs, alignItems: 'flex-end', justifyContent: 'center' },
});
