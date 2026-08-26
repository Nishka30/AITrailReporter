import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, minTouchSize, radii, spacing, type } from '../../theme/theme';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

type Props = {
  label: string;
  onPress: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  loading?: boolean;
  icon?: ReactNode;
  /** Full-width by default (the common case for primary screen actions). */
  fullWidth?: boolean;
  accessibilityHint?: string;
};

const VARIANT_STYLES: Record<ButtonVariant, { bg: string; border?: string; text: string }> = {
  primary: { bg: colors.marigold, text: colors.ink },
  secondary: { bg: colors.paperElevated, border: colors.borderStrong, text: colors.ink },
  ghost: { bg: 'transparent', text: colors.marigoldDeep },
  danger: { bg: colors.fix, text: colors.white },
};

/**
 * The one Button used everywhere in the app — variant controls emphasis,
 * never a hand-rolled Pressable style per screen. Meets the 48px minimum
 * touch target (Part L) regardless of label length.
 */
export default function Button({
  label,
  onPress,
  variant = 'primary',
  disabled = false,
  loading = false,
  icon,
  fullWidth = true,
  accessibilityHint,
}: Props) {
  const v = VARIANT_STYLES[variant];
  const isDisabled = disabled || loading;

  return (
    <Pressable
      onPress={onPress}
      disabled={isDisabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: isDisabled }}
      hitSlop={4}
      style={({ pressed }) => [
        styles.base,
        { backgroundColor: v.bg, borderColor: v.border ?? 'transparent', borderWidth: v.border ? 1 : 0 },
        fullWidth && styles.fullWidth,
        isDisabled && styles.disabled,
        pressed && !isDisabled && styles.pressed,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={v.text} />
      ) : (
        <View style={styles.content}>
          {icon}
          <Text style={[styles.label, { color: v.text }]} numberOfLines={1}>
            {label}
          </Text>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: minTouchSize,
    borderRadius: radii.pill,
    paddingHorizontal: spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  fullWidth: { alignSelf: 'stretch' },
  content: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  label: { ...type.button },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.85 },
});
