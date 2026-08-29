/**
 * Generates every TrailMind app-icon asset from the single logo source.
 *
 * Run:  node scripts/build-icons.js [path-to-logo.png]
 *
 * Uses jimp-compact, which is already present via @expo/image-utils — no new
 * dependency is added for branding work.
 *
 * WHY THIS IS NOT JUST "RESIZE THE LOGO SIX TIMES":
 *
 * 1. The source PNG has NO alpha channel and its rounded-card corners are
 *    filled with pure black. iOS and Android both apply their OWN mask to an
 *    app icon, so shipping those black corners produces a dark fringe around
 *    the finished icon on device. They are flood-filled back to the card's own
 *    cream before anything is exported.
 *
 * 2. Android adaptive icons crop the foreground to a circle/squircle and only
 *    the centre ~66% is guaranteed visible. The full lockup includes the
 *    "TrailMind" wordmark and tagline underneath the emblem, which that mask
 *    would slice straight through. So the Android foreground uses the EMBLEM
 *    ONLY, scaled into the safe zone — the wordmark is dropped deliberately
 *    rather than clipped accidentally.
 *
 * 3. The favicon is 48px, where the tagline is physically unreadable. It also
 *    uses the emblem rather than pretending the text will render.
 */

const fs = require('fs');
const path = require('path');
const Jimp = require('jimp-compact');

const SOURCE = process.argv[2] || 'C:/Users/user/OneDrive/Desktop/TrailMindLogo.png';
const ASSETS = path.join(__dirname, '..', 'assets');

// The card's own interior cream, sampled from the source rather than assumed,
// so the filled corners match the artwork exactly instead of "close enough".
const CREAM = { r: 252, g: 243, b: 223 };
// Brand ink, from src/theme/theme.ts, used for the monochrome silhouette.
const INK = { r: 33, g: 26, b: 20 };

// Emblem bounds measured from the source (head + mountain + trail, above the
// wordmark). Recompute these if the logo artwork is ever redrawn.
const EMBLEM = { x: 309, y: 145, w: 953 - 309, h: 838 - 145 };

/** Android adaptive-icon safe zone: keep art within the centre 66%. */
const SAFE_FRACTION = 0.66;

const lum = (p) => 0.299 * p.r + 0.587 * p.g + 0.114 * p.b;

/**
 * Replaces the black card corners with cream.
 *
 * Flood fill from the four corners rather than a global "recolour dark pixels"
 * pass: the artwork itself contains very dark ink (the head silhouette, the
 * wordmark) and a global rule would eat it. The fill cannot leak inward
 * because the card is ringed by a light tan border, so the dark interior is
 * never connected to the corners.
 *
 * The threshold is deliberately generous (<120) so the anti-aliased ramp
 * between black and the tan border is consumed too — a tighter threshold
 * leaves a visible grey halo once the platform mask is applied.
 */
function fillCorners(img) {
  const { width: W, height: H, data } = img.bitmap;
  const seen = new Uint8Array(W * H);
  const stack = [0, 0, W - 1, 0, 0, H - 1, W - 1, H - 1];

  while (stack.length) {
    const y = stack.pop();
    const x = stack.pop();
    if (x < 0 || y < 0 || x >= W || y >= H) continue;
    const i = y * W + x;
    if (seen[i]) continue;
    const o = i * 4;
    const p = { r: data[o], g: data[o + 1], b: data[o + 2] };
    if (lum(p) >= 120) continue;
    seen[i] = 1;
    data[o] = CREAM.r;
    data[o + 1] = CREAM.g;
    data[o + 2] = CREAM.b;
    data[o + 3] = 255;
    stack.push(x + 1, y, x - 1, y, x, y + 1, x, y - 1);
  }
  return img;
}

/** The emblem alone, cropped out of the full lockup. */
function cropEmblem(img) {
  return img.clone().crop(EMBLEM.x, EMBLEM.y, EMBLEM.w, EMBLEM.h);
}

/** Centres `art` inside a transparent square of `size`, scaled to the adaptive
 * safe zone so the platform's circular mask cannot clip it. */
async function onSafeCanvas(art, size, background) {
  const target = Math.round(size * SAFE_FRACTION);
  const scaled = art.clone();
  // contain() preserves aspect ratio; the emblem is not square.
  scaled.contain(target, target);
  const canvas = await new Jimp(size, size, background ?? 0x00000000);
  canvas.composite(scaled, Math.round((size - scaled.bitmap.width) / 2), Math.round((size - scaled.bitmap.height) / 2));
  return canvas;
}

/** Emblem as a flat ink silhouette on transparency, for Android themed icons. */
function toMonochrome(art) {
  const out = art.clone();
  out.scan(0, 0, out.bitmap.width, out.bitmap.height, function (x, y, idx) {
    const d = this.bitmap.data;
    const p = { r: d[idx], g: d[idx + 1], b: d[idx + 2] };
    // A themed icon is a stencil: every pixel is either ink or nothing.
    //
    // The cut-off sits at 175 rather than just below the cream ground (~245).
    // The mountain face in this artwork is a *textured* mid-grey whose pixels
    // straddle the higher value, so a near-cream threshold dithered it into
    // visible speckle. Cutting lower puts the whole rock face confidently on
    // one side of the line and keeps the silhouette clean at launcher size,
    // which is the only size this asset is ever seen at.
    const isArt = lum(p) < 175;
    d[idx] = INK.r;
    d[idx + 1] = INK.g;
    d[idx + 2] = INK.b;
    d[idx + 3] = isArt ? 255 : 0;
  });
  return out;
}

async function write(img, name) {
  const target = path.join(ASSETS, name);
  await img.writeAsync(target);
  const { size } = fs.statSync(target);
  console.log(`  ${name.padEnd(32)} ${img.bitmap.width}x${img.bitmap.height}  ${(size / 1024).toFixed(0)}KB`);
}

(async () => {
  if (!fs.existsSync(SOURCE)) {
    console.error(`Source logo not found: ${SOURCE}`);
    process.exit(1);
  }
  console.log(`Source: ${SOURCE}`);

  const master = fillCorners(await Jimp.read(SOURCE));
  const emblem = cropEmblem(master);

  console.log('Writing:');

  // Full lockup, full bleed — iOS and web apply their own corner mask.
  await write(master.clone().resize(1024, 1024), 'icon.png');
  await write(master.clone().resize(512, 512), 'splash-icon.png');

  // Emblem only below: the wordmark is unreadable or clipped at these sizes.
  await write((await onSafeCanvas(emblem, 1024)), 'android-icon-foreground.png');
  await write(
    await new Jimp(1024, 1024, Jimp.rgbaToInt(CREAM.r, CREAM.g, CREAM.b, 255)),
    'android-icon-background.png'
  );
  await write(await onSafeCanvas(toMonochrome(emblem), 1024), 'android-icon-monochrome.png');

  const favicon = emblem.clone();
  favicon.contain(48, 48);
  await write(favicon, 'favicon.png');

  console.log('Done.');
})().catch((err) => {
  console.error('Icon generation failed:', err);
  process.exit(1);
});
