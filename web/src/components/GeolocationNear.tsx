"use client";

import { useState } from "react";
import type { PublicLocationSummary } from "@/lib/content";
import { LocationCard } from "./LocationCard";

function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number) {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

type Status = "idle" | "loading" | "granted" | "denied" | "unsupported";

export function GeolocationNear({ locations }: { locations: PublicLocationSummary[] }) {
  const [status, setStatus] = useState<Status>("idle");
  const [nearby, setNearby] = useState<(PublicLocationSummary & { distanceKm: number })[]>([]);

  function request() {
    if (!("geolocation" in navigator)) {
      setStatus("unsupported");
      return;
    }
    setStatus("loading");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        const sorted = locations
          .map((l) => ({ ...l, distanceKm: distanceKm(latitude, longitude, l.latitude, l.longitude) }))
          .sort((a, b) => a.distanceKm - b.distanceKm)
          .slice(0, 3);
        setNearby(sorted);
        setStatus("granted");
      },
      () => setStatus("denied"),
      { timeout: 8000 },
    );
  }

  if (status === "idle" || status === "loading" || status === "unsupported") {
    return (
      <div className="flex flex-col items-start gap-4 rounded-[28px] border border-dashed border-border-strong bg-paper-muted/50 p-6 sm:flex-row sm:items-center sm:justify-between sm:p-7">
        <div>
          <p className="font-heading text-lg font-bold text-ink">See what&rsquo;s near you</p>
          <p className="mt-1 text-sm text-ink-soft">
            Optional — share your location to surface the closest places with recent reports.
          </p>
        </div>
        <button
          type="button"
          onClick={request}
          disabled={status === "loading"}
          className="shrink-0 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-paper transition-all duration-200 hover:-translate-y-0.5 hover:bg-marigold-deep hover:shadow-warm active:translate-y-0 disabled:opacity-60"
        >
          {status === "loading" ? "Locating…" : "Use my location"}
        </button>
      </div>
    );
  }

  if (status === "denied") {
    return (
      <p className="rounded-2xl border border-border bg-paper-muted/50 px-5 py-4 text-sm text-ink-soft">
        Location permission wasn&rsquo;t shared — that&rsquo;s okay, browse every place below instead.
      </p>
    );
  }

  if (nearby.length === 0) {
    return <p className="text-sm text-ink-soft">No places found near you yet.</p>;
  }

  return (
    <div className="grid gap-5 sm:grid-cols-3">
      {nearby.map((l) => (
        <div key={l.location_id} className="relative">
          <span className="absolute right-4 top-4 z-10 rounded-full bg-ink/80 px-2.5 py-1 text-[11px] font-semibold text-paper backdrop-blur-sm">
            {l.distanceKm < 1 ? "< 1 km away" : `${l.distanceKm.toFixed(1)} km away`}
          </span>
          <LocationCard location={l} />
        </div>
      ))}
    </div>
  );
}
