import clsx from "clsx";

const TILE = 256;
const COLS = 5;
const ROWS = 4;

function project(lat: number, lon: number, zoom: number): { x: number; y: number } {
  const n = 2 ** zoom;
  const rad = (lat * Math.PI) / 180;
  return {
    x: ((lon + 180) / 360) * n * TILE,
    y: ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * n * TILE,
  };
}

export interface MapTilePin {
  latitude: number;
  longitude: number;
  label?: string;
}

export const MAP_ATTRIBUTION = "Map © OpenStreetMap contributors";

/**
 * A static, non-interactive map of a real place -- the site's honest visual
 * when no guide photo exists. A small mosaic of map tiles centred on the
 * place, with its neighbours pinned. Pure markup: no map library, no JS.
 */
export function MapTile({
  center,
  pins = [],
  zoom = 15,
  className,
  muted = false,
  centerMarker = true,
  line = false,
  scale = 1,
}: {
  center: MapTilePin;
  pins?: MapTilePin[];
  zoom?: number;
  className?: string;
  muted?: boolean;
  /** Mark the centre as "this place" -- off for a route's bounding-box centre. */
  centerMarker?: boolean;
  /** Join the pins, in order, as a route line. */
  line?: boolean;
  /** Visual zoom between tile levels (e.g. 0.8 to fit a wide route). */
  scale?: number;
}) {
  const c = project(center.latitude, center.longitude, zoom);
  const firstX = Math.floor(c.x / TILE) - Math.floor(COLS / 2);
  const firstY = Math.floor(c.y / TILE) - Math.floor(ROWS / 2);
  const offsetX = c.x - firstX * TILE;
  const offsetY = c.y - firstY * TILE;
  const tiles: { x: number; y: number }[] = [];
  for (let row = 0; row < ROWS; row++) for (let col = 0; col < COLS; col++) tiles.push({ x: firstX + col, y: firstY + row });

  return (
    <div className={clsx("overflow-hidden bg-[#eef0ec]", className ?? "relative")} role="img" aria-label={`Map of ${center.label ?? "this place"}`}>
      <div
        className={clsx("absolute left-1/2 top-1/2 saturate-[.7]", muted && "opacity-90")}
        style={{ width: COLS * TILE, height: ROWS * TILE, transform: `translate(${-offsetX}px, ${-offsetY}px) scale(${scale})`, transformOrigin: `${offsetX}px ${offsetY}px` }}
      >
        {tiles.map((t) => (
          <div
            key={`${t.x}-${t.y}`}
            className="absolute bg-cover"
            style={{
              left: (t.x - firstX) * TILE,
              top: (t.y - firstY) * TILE,
              width: TILE,
              height: TILE,
              backgroundImage: `url(https://tile.openstreetmap.org/${zoom}/${t.x}/${t.y}.png)`,
            }}
          />
        ))}
        {line && pins.length > 1 && (
          <svg className="absolute inset-0 overflow-visible" width={COLS * TILE} height={ROWS * TILE} aria-hidden>
            <polyline
              points={pins
                .map((p) => {
                  const pt = project(p.latitude, p.longitude, zoom);
                  return `${pt.x - firstX * TILE},${pt.y - firstY * TILE}`;
                })
                .join(" ")}
              fill="none"
              stroke="#0a789b"
              strokeWidth={3.5}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </svg>
        )}
        {pins.map((p, i) => {
          const pt = project(p.latitude, p.longitude, zoom);
          return (
            <span
              key={i}
              title={p.label}
              className={clsx("absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white", line ? "h-3.5 w-3.5 bg-accent-deep" : "h-2.5 w-2.5 bg-[#4b7f93]")}
              style={{ left: pt.x - firstX * TILE, top: pt.y - firstY * TILE }}
            />
          );
        })}
        {centerMarker && (
          <span
            className="absolute flex h-5 w-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-[3px] border-white bg-accent-deep"
            style={{ left: offsetX, top: offsetY }}
          />
        )}
      </div>
    </div>
  );
}
