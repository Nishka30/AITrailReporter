/**
 * Deliberately mirrors mobile/src/theme/theme.ts's palette/type-scale values
 * exactly, rather than re-picking a "web-appropriate" palette — the admin
 * app must feel like the SAME product as the mobile app, just with a
 * denser, desktop-first layout. See src/theme/tokens.ts for the same values
 * exposed to plain TS/JS code (e.g. non-Tailwind inline styles, chart
 * colors) so the two never drift apart.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#211a14',
        'ink-soft': '#4a4038',
        'ink-faint': '#8a7d70',
        paper: '#faf4e9',
        'paper-elevated': '#ffffff',
        'paper-muted': '#f1e8d8',
        border: '#e7dcc7',
        'border-strong': '#d8c9ab',
        marigold: '#e8a13c',
        'marigold-deep': '#c9821f',
        'marigold-soft': '#fbe7c5',
        ok: '#1f6f4a',
        'ok-soft': '#dcefe3',
        fix: '#b8391f',
        'fix-soft': '#f7dfd7',
        info: '#2f5f8a',
        'info-soft': '#dce8f2',
        'neutral-soft': '#efe7d8',
      },
      fontFamily: {
        heading: ['"Bricolage Grotesque"', 'system-ui', 'sans-serif'],
        body: ['"Atkinson Hyperlegible"', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        sm: '10px',
        md: '14px',
        lg: '18px',
        xl: '24px',
      },
      boxShadow: {
        card: '0 2px 8px 0 rgb(33 26 20 / 0.06)',
      },
    },
  },
  plugins: [],
};
