import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing, type } from '../../theme/theme';

export type TabKey = 'home' | 'questions' | 'activity';

type TabDef = {
  key: TabKey;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  iconActive: keyof typeof Ionicons.glyphMap;
};

const TABS: TabDef[] = [
  { key: 'home', label: 'Home', icon: 'home-outline', iconActive: 'home' },
  { key: 'questions', label: 'Questions', icon: 'chatbubble-ellipses-outline', iconActive: 'chatbubble-ellipses' },
  { key: 'activity', label: 'Activity', icon: 'time-outline', iconActive: 'time' },
];

type Props = {
  active: TabKey;
  onChange: (tab: TabKey) => void;
  /** Small numeric badges, keyed by tab — omitted/0/null renders no badge.
   * Never fabricated: callers only pass a number once they've actually
   * loaded it (see RootNavigator.tsx). */
  badges?: Partial<Record<TabKey, number | null>>;
};

/**
 * A lightweight, dependency-free bottom tab bar (Part E: navigation may
 * improve, but no navigation library). RootNavigator renders this alongside
 * whichever tab-root screen is active, and hides it for pushed screens
 * (CreateNote, AnswerQuestion, Setup) — those keep their own back-button
 * header instead, exactly like a stack push.
 */
export default function TabBar({ active, onChange, badges }: Props) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.container, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
      {TABS.map((tab) => {
        const isActive = tab.key === active;
        const badgeValue = badges?.[tab.key];
        return (
          <Pressable
            key={tab.key}
            onPress={() => onChange(tab.key)}
            accessibilityRole="tab"
            accessibilityState={{ selected: isActive }}
            accessibilityLabel={tab.label}
            style={styles.tab}
            hitSlop={4}
          >
            <View>
              <Ionicons
                name={isActive ? tab.iconActive : tab.icon}
                size={24}
                color={isActive ? colors.marigoldDeep : colors.inkFaint}
              />
              {badgeValue ? (
                <View style={styles.badge}>
                  <Text style={styles.badgeText} numberOfLines={1}>
                    {badgeValue > 9 ? '9+' : String(badgeValue)}
                  </Text>
                </View>
              ) : null}
            </View>
            <Text style={[styles.label, isActive && styles.labelActive]}>{tab.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    backgroundColor: colors.paperElevated,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.xs,
  },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 2, minHeight: 44 },
  label: { ...type.caption, color: colors.inkFaint },
  labelActive: { color: colors.marigoldDeep, fontFamily: type.captionBold.fontFamily },
  badge: {
    position: 'absolute',
    top: -4,
    right: -10,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    paddingHorizontal: 3,
    backgroundColor: colors.fix,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: { fontSize: 10, lineHeight: 12, color: colors.white, fontFamily: type.captionBold.fontFamily },
});
