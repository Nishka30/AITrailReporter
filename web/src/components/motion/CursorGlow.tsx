"use client";

import { useRef } from "react";
import { motion, useMotionValue, useSpring } from "motion/react";

/** A soft, spring-damped glow that follows the pointer within its parent --
 * a subtle ambient touch, not a gimmick: low opacity, generously blurred,
 * and inert on touch devices (no pointer to follow). Parent must be
 * `relative` and `overflow-hidden`. */
export function CursorGlow() {
  const ref = useRef<HTMLDivElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { damping: 30, stiffness: 120 });
  const springY = useSpring(y, { damping: 30, stiffness: 120 });

  function onMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    x.set(e.clientX - rect.left);
    y.set(e.clientY - rect.top);
  }

  return (
    <div ref={ref} onMouseMove={onMouseMove} className="absolute inset-0 hidden sm:block">
      <motion.div
        className="pointer-events-none absolute h-[420px] w-[420px] rounded-full bg-marigold/25 blur-[100px]"
        style={{ left: springX, top: springY, translateX: "-50%", translateY: "-50%" }}
      />
    </div>
  );
}
