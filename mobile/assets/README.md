# TrailMind app icons

All icon PNGs in this folder are **generated** from a single logo source by
`scripts/build-icons.js`. Do not hand-edit them — regenerate instead, or the
next run will overwrite your changes.

```bash
node scripts/build-icons.js [path-to-logo.png]
```

The default source path is `C:/Users/user/OneDrive/Desktop/TrailMindLogo.png`.
Pass a different path as the first argument if the master artwork moves.

Icons are baked in at **build** time, so Fast Refresh will not show a change —
rebuild the app (or reinstall the dev client) to see a new icon on device.

## What gets generated

| File | Size | Content |
|---|---|---|
| `icon.png` | 1024×1024 | Full lockup (emblem + wordmark + tagline), full bleed |
| `splash-icon.png` | 512×512 | Full lockup |
| `android-icon-foreground.png` | 1024×1024 | **Emblem only**, inside the adaptive safe zone |
| `android-icon-background.png` | 1024×1024 | Flat card cream `#fcf3df` |
| `android-icon-monochrome.png` | 1024×1024 | Emblem as an ink stencil on transparency |
| `favicon.png` | 48×48 | **Emblem only** |

`.original-expo-icons/` holds the Expo starter defaults that these replaced,
in case a clean comparison is ever needed.

## Three things the script handles that a plain resize would not

1. **The source has no alpha, and its rounded-card corners are pure black.**
   iOS and Android both apply their own mask to an app icon, so shipping those
   corners produces a dark fringe around the finished icon. They are
   flood-filled back to the card's own cream first. The fill starts from the
   four corners rather than recolouring all dark pixels globally — the artwork
   itself contains near-black ink, and a global rule would eat the head
   silhouette and the wordmark.

2. **Android crops the adaptive foreground to a circle.** Only the centre ~66%
   is guaranteed visible, and that mask would slice straight through the
   "TrailMind" wordmark and tagline. The Android foreground therefore uses the
   **emblem only**, scaled into the safe zone — the wordmark is dropped
   deliberately rather than clipped accidentally.

3. **The favicon is 48px**, where the tagline is physically unreadable. It also
   uses the emblem rather than pretending the text will render.

## If the artwork is ever redrawn

`EMBLEM` in `scripts/build-icons.js` holds the measured pixel bounds of the
emblem within the full lockup (currently `x 309–953, y 145–838` in the
1254×1254 source). Re-measure and update it if the composition changes, or the
Android foreground will crop the wrong region.

## Brand palette

Taken from `src/theme/theme.ts`, with the card cream sampled from the artwork:

| Role | Hex |
|---|---|
| Card cream (icon ground) | `#fcf3df` |
| App paper | `#faf4e9` |
| Ink | `#211a14` |
| Marigold | `#e8a13c` |
| Marigold deep | `#c9821f` |
