/**
 * The app's small design system (Step 15) — a single source of truth for
 * color, spacing, radius, and type so screens stop repeating arbitrary
 * StyleSheet values. Palette is inspired by the field-tool reference design
 * (ink / marigold / paper / ok / fix) but re-picked for this app rather than
 * pixel-matched — see mobile/README.md's Step 15 section for the full
 * design rationale.
 */

export const colors = {
  // Warm, calm neutrals — the base of every screen.
  ink: '#211a14', // primary text, primary (dark) surfaces
  inkSoft: '#4a4038', // secondary text
  inkFaint: '#8a7d70', // tertiary/meta text
  paper: '#faf4e9', // app background
  paperElevated: '#ffffff', // cards/surfaces sitting above the background
  paperMuted: '#f1e8d8', // subtle recessed surface (e.g. inputs, chips)
  border: '#e7dcc7', // hairline borders on warm backgrounds
  borderStrong: '#d8c9ab',

  // Brand accent — the one primary action color. Used deliberately, not
  // scattered: primary buttons, active/focus states, key highlights.
  marigold: '#e8a13c',
  marigoldDeep: '#c9821f', // pressed/text-on-light variant
  marigoldSoft: '#fbe7c5', // tinted backgrounds (badges, highlight cards)

  // Status colors — used ONLY for status communication (badges, sync
  // states), never as decoration, so their meaning stays reliable.
  ok: '#1f6f4a',
  okSoft: '#dcefe3',
  fix: '#b8391f',
  fixSoft: '#f7dfd7',
  info: '#2f5f8a',
  infoSoft: '#dce8f2',
  neutralSoft: '#efe7d8',

  white: '#ffffff',
  black: '#000000',
} as const;

export const spacing = {
  xxs: 4,
  xs: 8,
  sm: 12,
  md: 16,
  lg: 20,
  xl: 24,
  xxl: 32,
  xxxl: 40,
} as const;

export const radii = {
  sm: 10,
  md: 14,
  lg: 18,
  xl: 24,
  pill: 999,
} as const;

/**
 * Font families. Bricolage Grotesque (bold/extrabold) for headings gives the
 * app a distinctive, confident voice; Atkinson Hyperlegible for body text is
 * a typeface specifically designed for legibility in low-vision and
 * high-glare conditions — directly relevant to a guide reading a phone
 * outdoors in bright sun. Loaded via useAppFonts() (src/theme/fonts.ts);
 * every screen must render only after that resolves (see App.tsx) so these
 * names are always safe to reference.
 */
export const fonts = {
  headingBold: 'BricolageGrotesque_700Bold',
  headingExtraBold: 'BricolageGrotesque_800ExtraBold',
  headingSemiBold: 'BricolageGrotesque_600SemiBold',
  body: 'AtkinsonHyperlegible_400Regular',
  bodyBold: 'AtkinsonHyperlegible_700Bold',
} as const;

export const type = {
  display: { fontFamily: fonts.headingExtraBold, fontSize: 30, lineHeight: 36 },
  title: { fontFamily: fonts.headingBold, fontSize: 22, lineHeight: 28 },
  subtitle: { fontFamily: fonts.headingSemiBold, fontSize: 17, lineHeight: 23 },
  body: { fontFamily: fonts.body, fontSize: 16, lineHeight: 23 },
  bodyBold: { fontFamily: fonts.bodyBold, fontSize: 16, lineHeight: 23 },
  small: { fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  smallBold: { fontFamily: fonts.bodyBold, fontSize: 13, lineHeight: 18 },
  caption: { fontFamily: fonts.body, fontSize: 12, lineHeight: 16 },
  captionBold: { fontFamily: fonts.bodyBold, fontSize: 12, lineHeight: 16 },
  button: { fontFamily: fonts.headingSemiBold, fontSize: 16, lineHeight: 20 },
} as const;

/** A single, subtle elevation used for every raised card — one consistent
 * "lift" language instead of ad-hoc shadow values per screen. */
export const shadow = {
  card: {
    shadowColor: colors.ink,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },
} as const;

/** Minimum touch target size (Part L) — applied via hitSlop/minHeight on
 * every interactive control in src/components/ui. */
export const minTouchSize = 48;
