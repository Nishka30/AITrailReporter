import {
  useFonts as useAtkinsonFonts,
  AtkinsonHyperlegible_400Regular,
  AtkinsonHyperlegible_700Bold,
} from '@expo-google-fonts/atkinson-hyperlegible';
import {
  useFonts as useBricolageFonts,
  BricolageGrotesque_600SemiBold,
  BricolageGrotesque_700Bold,
  BricolageGrotesque_800ExtraBold,
} from '@expo-google-fonts/bricolage-grotesque';

/**
 * Loads every font family referenced by src/theme/theme.ts's `fonts` object.
 * Returns true once both font sets have resolved — App.tsx must not render
 * RootNavigator until this is true (see App.tsx), otherwise text would
 * render in the platform default font for a flash, or (worse) a
 * fontFamily lookup could silently no-op on some platforms.
 */
export function useAppFonts(): boolean {
  const [bricolageLoaded] = useBricolageFonts({
    BricolageGrotesque_600SemiBold,
    BricolageGrotesque_700Bold,
    BricolageGrotesque_800ExtraBold,
  });
  const [atkinsonLoaded] = useAtkinsonFonts({
    AtkinsonHyperlegible_400Regular,
    AtkinsonHyperlegible_700Bold,
  });
  return bricolageLoaded && atkinsonLoaded;
}
