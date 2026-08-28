"use client";

import { useRef, useState } from "react";

export function VoicePlayer({
  audioUrl,
  transcript,
  guideName,
}: {
  audioUrl: string | null;
  transcript: string | null;
  guideName: string;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [expanded, setExpanded] = useState(!audioUrl);

  function toggle() {
    const el = audioRef.current;
    if (!el) return;
    if (playing) {
      el.pause();
    } else {
      el.play();
    }
  }

  return (
    <div className="rounded-[28px] border border-border/70 bg-paper-elevated p-6 shadow-warm sm:p-7">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={toggle}
          disabled={!audioUrl}
          aria-label={playing ? "Pause" : "Play"}
          className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-ink text-paper transition-transform duration-200 hover:scale-105 hover:bg-marigold-deep active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {playing ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="5" width="4" height="14" rx="1" />
              <rect x="14" y="5" width="4" height="14" rx="1" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>
        <div className="min-w-0">
          <p className="font-heading text-base font-bold text-ink">A story from the trail</p>
          <p className="text-sm text-ink-faint">Told by {guideName}</p>
        </div>
        {transcript && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="ml-auto shrink-0 text-xs font-semibold text-marigold-deep underline-offset-2 hover:underline"
          >
            {expanded ? "Hide transcript" : "Read transcript"}
          </button>
        )}
      </div>
      {!audioUrl && (
        <p className="mt-4 text-xs text-ink-faint">
          Audio playback isn&rsquo;t connected for this demo report — reading the transcript below.
        </p>
      )}
      {audioUrl && (
        <audio
          ref={audioRef}
          src={audioUrl}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          className="mt-4 hidden"
        />
      )}
      {expanded && transcript && (
        <p className="mt-5 border-t border-border pt-5 text-[15px] italic leading-relaxed text-ink-soft">
          &ldquo;{transcript}&rdquo;
        </p>
      )}
    </div>
  );
}
