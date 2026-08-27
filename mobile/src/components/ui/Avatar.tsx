import { Image, Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native';

import { colors, type } from '../../theme/theme';

type Props = {
  /** The guide's name — used only to derive initials when there is no photo. */
  name: string;
  /** On-device profile photo path, or null. Shown instead of initials when set. */
  photoUri?: string | null;
  size?: number;
  onPress?: () => void;
  accessibilityLabel?: string;
  style?: ViewStyle;
};

/**
 * The guide's avatar (Step 17), shared by the Home header, the Profile screen
 * and Setup so all three always agree on how the user is represented.
 *
 * Renders the profile photo when one exists, and otherwise falls back to the
 * initial derived from the current name. That fallback is the reason initials
 * update the moment a name is saved and the moment a photo is removed — there
 * is only one rule, in one place, rather than each screen slicing the name
 * itself (which is what Home used to do).
 *
 * Type scales with `size` so a 96pt profile avatar and a 52pt header avatar
 * both look deliberate rather than one being a stretched copy of the other.
 */
export default function Avatar({
  name,
  photoUri,
  size = 52,
  onPress,
  accessibilityLabel,
  style,
}: Props) {
  // `?? '?'` covers a name that is empty or made entirely of whitespace — a
  // blank circle would look like a rendering bug rather than a missing name.
  const initial = name.trim().charAt(0).toUpperCase() || '?';

  const frame = { width: size, height: size, borderRadius: size / 2 };

  const content = photoUri ? (
    <Image
      source={{ uri: photoUri }}
      style={[styles.image, frame]}
      resizeMode="cover"
      accessibilityIgnoresInvertColors
    />
  ) : (
    <View style={[styles.initialsCircle, frame]}>
      <Text style={[styles.initialsText, { fontSize: size * 0.42, lineHeight: size * 0.5 }]}>
        {initial}
      </Text>
    </View>
  );

  if (!onPress) {
    return <View style={style}>{content}</View>;
  }

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? 'Open your profile'}
      hitSlop={8}
      style={({ pressed }) => [style, pressed && styles.pressed]}
    >
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  image: { backgroundColor: colors.paperMuted },
  initialsCircle: {
    backgroundColor: colors.ink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  initialsText: { fontFamily: type.title.fontFamily, color: colors.marigoldSoft },
  pressed: { opacity: 0.75 },
});
