"use client";

import { useEffect, useRef, useState } from "react";
import { useInView, animate } from "motion/react";

/** Animates a real, already-known number counting up once it scrolls into
 * view -- never displayed before the true value is known, so it can't lie
 * mid-animation the way a fake "loading counter" would. */
export function CountUp({ value, className }: { value: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!inView) return;
    const controls = animate(0, value, {
      duration: 1.1,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    return () => controls.stop();
  }, [inView, value]);

  return (
    <span ref={ref} className={className}>
      {display}
    </span>
  );
}
