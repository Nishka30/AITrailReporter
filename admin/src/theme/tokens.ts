/**
 * Plain TS mirror of tailwind.config.js's palette, for the rare spot that
 * needs a raw value instead of a Tailwind class (e.g. an inline SVG stroke
 * color on a map marker). Keep these two files in sync by hand -- there are
 * few enough colors that a build-time codegen step would be overkill.
 */
export const colors = {
  ink: '#211a14',
  inkSoft: '#4a4038',
  inkFaint: '#8a7d70',
  paper: '#faf4e9',
  paperElevated: '#ffffff',
  paperMuted: '#f1e8d8',
  border: '#e7dcc7',
  borderStrong: '#d8c9ab',
  marigold: '#e8a13c',
  marigoldDeep: '#c9821f',
  marigoldSoft: '#fbe7c5',
  ok: '#1f6f4a',
  okSoft: '#dcefe3',
  fix: '#b8391f',
  fixSoft: '#f7dfd7',
  info: '#2f5f8a',
  infoSoft: '#dce8f2',
  neutralSoft: '#efe7d8',
} as const;
