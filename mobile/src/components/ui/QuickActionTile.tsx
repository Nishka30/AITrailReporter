import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { colors, minTouchSize, radii, spacing, type } from '../../theme/theme';

type Props = {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  /** A tile mid-action (e.g. recording) gets the brand fill instead of the
   * neutral one, so its state is unmistakable at a glance. */
  active?: boolean;
  disabled?: boolean;
};

/** One of Home's primary "do something" actions (Add note / Record voice /
 * Capture location) — square icon tile + label, sized well above the
 * minimum touch target for reliable outdoor/gloved use. */
export default function QuickActionTile({ icon, label, onPress, active = false, disabled = false }: Props) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [
        styles.tile,
        active && styles.tileActive,
        disabled && styles.disabled,
        pressed && !disabled && styles.pressed,
      ]}
    >
      <View style={[styles.iconCircle, active && styles.iconCircleActive]}>
        <Ionicons name={icon} size={22} color={active ? colors.ink : colors.marigoldDeep} />
      </View>
      <Text style={[styles.label, active && styles.labelActive]} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  tile: {
    flex: 1,
    minHeight: minTouchSize + 28,
    borderRadius: radii.lg,
    backgroundColor: colors.paperElevated,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
    gap: spacing.xs,
  },
  tileActive: { backgroundColor: colors.marigold, borderColor: colors.marigold },
  iconCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.marigoldSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconCircleActive: { backgroundColor: 'rgba(33,26,20,0.12)' },
  label: { ...type.captionBold, color: colors.ink, textAlign: 'center' },
  labelActive: { color: colors.ink },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.85 },
});
