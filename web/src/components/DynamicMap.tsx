"use client";

import dynamic from "next/dynamic";

// Leaflet touches `window` at module scope, so the map must never render on
// the server -- this is the one legitimate ssr:false boundary in the app.
export const DynamicMap = dynamic(() => import("./MapView").then((m) => m.MapView), {
  ssr: false,
  loading: () => (
    <div className="flex h-[360px] items-center justify-center rounded-3xl border border-border bg-paper-muted text-sm text-ink-faint">
      Loading map…
    </div>
  ),
});
