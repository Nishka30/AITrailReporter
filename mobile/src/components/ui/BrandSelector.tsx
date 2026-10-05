import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { colors, minTouchSize, spacing, type } from '../../theme/theme';

/**
 * The four tour-operator brands a guide may be affiliated with. Short codes
 * mirror the backend's GUIDE_BRANDS exactly (app/db/models/guide.py) -- these
 * are the ONLY four supported values; there is no "other" / free-text option.
 */
export const BRAND_OPTIONS = [
  { code: 'BCT', label: 'BaseCampTours' },
  { code: 'HW', label: 'HimalayanWonders' },
  { code: 'TH', label: 'TrekkingHero' },
  { code: 'PH', label: 'PatagoniaHero' },
] as const;

export type BrandCode = (typeof BRAND_OPTIONS)[number]['code'];

/** "BaseCampTours (BCT)" -- the one place this display format is built, so
 * the profile summary line and any future caller never drift apart. */
export function brandDisplayName(code: string): string {
  const match = BRAND_OPTIONS.find((b) => b.code === code);
  return match ? `${match.label} (${match.code})` : code;
}

/** "BaseCampTours (BCT) · HimalayanWonders (HW)" -- joins in BRAND_OPTIONS
 * order regardless of the input order, so the summary reads consistently
 * no matter which order a guide checked the boxes in. */
export function formatBrands(codes: string[] | null | undefined): string | null {
  if (!codes || codes.length === 0) return null;
  const ordered = BRAND_OPTIONS.filter((b) => codes.includes(b.code));
  return ordered.map((b) => brandDisplayName(b.code)).join(' · ');
}

type Props = {
  selected: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
  /** Shown under the checkbox list only once the guide has touched it and
   * left every box unchecked -- matches the phone-number field's pattern of
   * not scolding an untouched field (see SetupScreen/ProfileScreen). */
  showEmptyWarning?: boolean;
};

/**
 * "Which brand(s) do you belong to?" -- a multi-select checkbox list over the
 * four controlled BRAND_OPTIONS. Plain Pressable + Ionicons, matching this
 * app's existing form idiom (no form library, no third-party checkbox
 * component exists anywhere in this codebase).
 */
export default function BrandSelector({ selected, onChange, disabled, showEmptyWarning }: Props) {
  function toggle(code: string) {
    if (disabled) return;
    onChange(selected.includes(code) ? selected.filter((c) => c !== code) : [...selected, code]);
  }

  return (
    <View>
      {BRAND_OPTIONS.map((option) => {
        const checked = selected.includes(option.code);
        return (
          <Pressable
            key={option.code}
            onPress={() => toggle(option.code)}
            disabled={disabled}
            accessibilityRole="checkbox"
            accessibilityState={{ checked, disabled }}
            accessibilityLabel={`${option.label} (${option.code})`}
            style={({ pressed }) => [styles.row, pressed && styles.pressed]}
          >
            <View style={[styles.checkbox, checked && styles.checkboxChecked]}>
              {checked ? <Ionicons name="checkmark" size={14} color={colors.white} /> : null}
            </View>
            <Text style={styles.label}>
              {option.label} <Text style={styles.code}>({option.code})</Text>
            </Text>
          </Pressable>
        );
      })}
      {showEmptyWarning && selected.length === 0 ? (
        <Text style={styles.warning}>Select at least one brand.</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  pressed: { opacity: 0.75 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    minHeight: minTouchSize,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.paperElevated,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxChecked: {
    borderColor: colors.marigoldDeep,
    backgroundColor: colors.marigoldDeep,
  },
  label: { ...type.body, color: colors.ink },
  code: { color: colors.inkFaint },
  warning: { ...type.caption, color: colors.fix, marginTop: 2, marginBottom: spacing.xs },
});
