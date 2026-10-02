"use client";

import Image from "next/image";
import { useState } from "react";
import type { PublicObservation } from "@/lib/content";
import { timeAgoLabel } from "@/lib/content/freshness";

interface Photo {
  url: string;
  observation: PublicObservation;
}

export function PhotoGrid({ observations }: { observations: PublicObservation[] }) {
  // One tile per PHOTO, not per observation -- a single observation can now
  // carry several photos (multi-photo submissions).
  const photos: Photo[] = observations
    .filter((o) => o.has_photo)
    .flatMap((o) => o.photo_urls.map((url) => ({ url, observation: o })));
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  if (photos.length === 0) return null;
  const active = openIndex !== null ? photos[openIndex] : null;

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        {photos.map((p, i) => (
          <button
            key={p.url}
            type="button"
            onClick={() => setOpenIndex(i)}
            className="group relative aspect-square overflow-hidden rounded-[6px] bg-paper-muted"
          >
            <Image
              src={p.url}
              alt=""
              fill
              sizes="(min-width: 768px) 25vw, 50vw"
              className="object-cover transition duration-500 group-hover:scale-[1.04]"
            />
          </button>
        ))}
      </div>

      {active && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/90 p-4 sm:p-10"
          onClick={() => setOpenIndex(null)}
        >
          <button
            type="button"
            aria-label="Close"
            onClick={() => setOpenIndex(null)}
            className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full bg-paper/10 text-paper transition hover:bg-paper/20"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
          <div
            className="relative flex max-h-full max-w-4xl flex-col overflow-hidden rounded-[8px] bg-ink"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="relative aspect-[4/3] w-full max-h-[70vh]">
              <Image src={active.url} alt="" fill sizes="90vw" className="object-contain" />
            </div>
            <div className="bg-white p-5">
              {active.observation.evidence && (
                <p className="text-[15px] leading-relaxed text-ink">{active.observation.evidence}</p>
              )}
              <p className="mt-2 text-xs text-ink-faint">
                Captured by {active.observation.guide_name} · {timeAgoLabel(active.observation.observed_at)}
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
