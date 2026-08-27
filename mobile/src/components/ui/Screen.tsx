import type { ReactNode } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View, type ScrollViewProps } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing } from '../../theme/theme';

type Props = {
  children: ReactNode;
  /** Scrollable by default (most screens are lists/forms) — pass false for a
   * screen that manages its own ScrollView/FlatList internally. */
  scroll?: boolean;
  /** Extra bottom padding when a fixed footer/tab bar overlaps content. */
  footerSpace?: number;
  contentContainerStyle?: ScrollViewProps['contentContainerStyle'];
  /** Wires native pull-to-refresh to a real async refresh function — still a
   * user-initiated action, not polling (see QuestionsScreen.tsx). Omit for
   * screens with nothing worth manually re-fetching. */
  onRefresh?: () => void | Promise<void>;
  refreshing?: boolean;
};

/**
 * Shared screen shell: safe-area-aware (top only — bottom is handled by
 * whatever renders below, e.g. the tab bar, so content doesn't double-pad),
 * consistent horizontal padding and background. Every screen should be
 * wrapped in this instead of a bare `View`/`StyleSheet.create({ container })`
 * so safe areas and background color are never re-derived per screen (Part L).
 */
export default function Screen({
  children,
  scroll = true,
  footerSpace = 0,
  contentContainerStyle,
  onRefresh,
  refreshing = false,
}: Props) {
  const insets = useSafeAreaInsets();

  if (!scroll) {
    return (
      <View style={[styles.base, { paddingTop: insets.top + spacing.md }]}>{children}</View>
    );
  }

  return (
    <ScrollView
      style={styles.base}
      contentContainerStyle={[
        {
          paddingTop: insets.top + spacing.md,
          paddingBottom: spacing.xxl + footerSpace,
        },
        contentContainerStyle,
      ]}
      keyboardShouldPersistTaps="handled"
      refreshControl={
        onRefresh ? (
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            // `tintColor` is iOS-ONLY. Android reads `colors` (an array) and
            // `progressBackgroundColor` — without them Android falls back to
            // its stock blue spinner, which is why the indicator appeared in a
            // colour that exists nowhere in this app's palette.
            tintColor={colors.marigoldDeep}
            colors={[colors.marigoldDeep]}
            progressBackgroundColor={colors.paperElevated}
          />
        ) : undefined
      }
    >
      {children}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  base: {
    flex: 1,
    backgroundColor: colors.paper,
    paddingHorizontal: spacing.lg,
  },
});
