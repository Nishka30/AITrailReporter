import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { colors, radii, shadow, spacing } from '../../theme/theme';

type Props = {
  children: ReactNode;
  onPress?: () => void;
  /** 'raised' (default): white surface with a soft shadow, for content
   * sitting on the paper background. 'flat': a tinted, borderless recessed
   * surface — for secondary/nested content that shouldn't compete visually
   * (e.g. a row inside another card). 'outline': bordered, transparent —
   * for emphasis without weight (e.g. a highlighted but non-primary card). */
  variant?: 'raised' | 'flat' | 'outline';
  style?: StyleProp<ViewStyle>;
  accessibilityLabel?: string;
};

export default function Card({ children, onPress, variant = 'raised', style, accessibilityLabel }: Props) {
  const variantStyle =
    variant === 'flat' ? styles.flat : variant === 'outline' ? styles.outline : styles.raised;

  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel}
        style={({ pressed }) => [styles.base, variantStyle, pressed && styles.pressed, style]}
      >
        {children}
      </Pressable>
    );
  }

  return <View style={[styles.base, variantStyle, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  base: { borderRadius: radii.lg, padding: spacing.md },
  raised: { backgroundColor: colors.paperElevated, ...shadow.card },
  flat: { backgroundColor: colors.paperMuted },
  outline: { backgroundColor: colors.paperElevated, borderWidth: 1, borderColor: colors.border },
  pressed: { opacity: 0.9 },
});
