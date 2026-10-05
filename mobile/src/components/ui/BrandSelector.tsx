import { Pressable, StyleSheet, Text, View } from 'react-native';

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

/** "BaseCampTours (BCT)", or null when no brand is recorded -- the one place
 * the profile's read-only summary line is built. */
export function formatBrand(code: string | null | undefined): string | null {
  if (!code) return null;
  return brandDisplayName(code);
}

type Props = {
  selected: string | null;
  onChange: (next: string | null) => void;
  disabled?: boolean;
  /** Shown under the radio list only once the guide has touched it and left
   * nothing selected -- matches the phone-number field's pattern of not
   * scolding an untouched field (see SetupScreen/ProfileScreen). */
  showEmptyWarning?: boolean;
};

/**
 * "Which brand do you belong to?" -- a single-select radio list over the four
 * controlled BRAND_OPTIONS. A guide belongs to exactly one brand, so picking
 * a new option replaces the previous selection rather than adding to it.
 * Plain Pressable + Ionicons, matching this app's existing form idiom (no
 * form library, no third-party radio component exists anywhere in this
 * codebase).
 */
export default function BrandSelector({ selected, onChange, disabled, showEmptyWarning }: Props) {
  function select(code: string) {
    if (disabled) return;
    onChange(code);
  }

  return (
    <View>
      {BRAND_OPTIONS.map((option) => {
        const checked = selected === option.code;
        return (
          <Pressable
            key={option.code}
            onPress={() => select(option.code)}
            disabled={disabled}
            accessibilityRole="radio"
            accessibilityState={{ checked, disabled }}
            accessibilityLabel={`${option.label} (${option.code})`}
            style={({ pressed }) => [styles.row, pressed && styles.pressed]}
          >
            <View style={[styles.radio, checked && styles.radioChecked]}>
              {checked ? <View style={styles.radioDot} /> : null}
            </View>
            <Text style={styles.label}>
              {option.label} <Text style={styles.code}>({option.code})</Text>
            </Text>
          </Pressable>
        );
      })}
      {showEmptyWarning && !selected ? (
        <Text style={styles.warning}>Select a brand.</Text>
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
  radio: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.paperElevated,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioChecked: {
    borderColor: colors.marigoldDeep,
  },
  radioDot: {
    width: 11,
    height: 11,
    borderRadius: 5.5,
    backgroundColor: colors.marigoldDeep,
  },
  label: { ...type.body, color: colors.ink },
  code: { color: colors.inkFaint },
  warning: { ...type.caption, color: colors.fix, marginTop: 2, marginBottom: spacing.xs },
});
