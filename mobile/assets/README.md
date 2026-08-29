# TrailMind app icons

`trailmind-icon.svg` is the design source of truth. Its palette is copied
verbatim from `src/theme/theme.ts`, so the icon and the app cannot drift apart.

## Current status

**The PNGs in this folder are still the Expo starter defaults.** The SVG above
is the TrailMind mark, but nothing rasterizes SVG at build time — Expo needs
PNGs — so the launcher icon does not change until the files below are
regenerated. `app.json` already points at the correct filenames and the
adaptive-icon background is already set to the brand cream (`#faf4e9`), so
replacing the files is the only remaining step.

## Regenerating

Any SVG rasterizer works. With `sharp-cli` (no Python/native image deps):

```bash
npx sharp-cli -i assets/trailmind-icon.svg -o assets/icon.png resize 1024 1024
npx sharp-cli -i assets/trailmind-icon.svg -o assets/android-icon-foreground.png resize 1024 1024
npx sharp-cli -i assets/trailmind-icon.svg -o assets/favicon.png resize 48 48
npx sharp-cli -i assets/trailmind-icon.svg -o assets/splash-icon.png resize 512 512
```

Then rebuild — icons are baked in at build time, so Fast Refresh will not show
the change.

| File | Size | Notes |
|---|---|---|
| `icon.png` | 1024×1024 | iOS + fallback. No transparency; iOS masks corners itself. |
| `android-icon-foreground.png` | 1024×1024 | Adaptive foreground. Keep art inside the centre 66% — the SVG already does. |
| `android-icon-background.png` | 1024×1024 | Flat `#faf4e9`. Can also be dropped in favour of the `backgroundColor` already set in `app.json`. |
| `android-icon-monochrome.png` | 1024×1024 | Themed icons: silhouette only, ink on transparent. Drop the marigold fill. |
| `favicon.png` | 48×48 | Web. |
| `splash-icon.png` | 512×512 | Splash. |

## Constraints the mark is built to

- Warm paper/cream ground, ink linework, marigold accent — the app's palette.
- Legible at 48px; two colours only, so greyscale and monochrome export survive.
- No gradients (they band at launcher sizes and break monochrome export).
- Deliberately not a mountain range or compass rose — the brief explicitly
  ruled out generic outdoor-tourism marks.
