"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Icon } from "./Icons";

export interface SectionNavItem {
  id: string;
  label: string;
}

/** Offset (px) at which a section counts as "the one you're reading" --
 * just under this bar's own height. */
const ACTIVE_LINE = 96;

/**
 * The reference guide's in-page tab bar: pinned to the top of the viewport
 * once the header has scrolled away, the tab for the section in view is
 * underlined, and a tab click smooth-scrolls (html scroll-behavior) to its
 * section. Only sections that actually rendered are passed in.
 */
export function SectionNav({
  items,
  label,
  action,
}: {
  items: SectionNavItem[];
  label?: string;
  action?: { href: string; label: string; filled?: boolean };
}) {
  const [active, setActive] = useState<string | null>(items[0]?.id ?? null);
  const railRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      let current: string | null = items[0]?.id ?? null;
      for (const item of items) {
        const el = document.getElementById(item.id);
        if (el && el.getBoundingClientRect().top <= ACTIVE_LINE) current = item.id;
      }
      const atBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 4;
      if (atBottom && items.length) current = items[items.length - 1].id;
      setActive(current);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [items]);

  useEffect(() => {
    const rail = railRef.current;
    const tab = rail?.querySelector<HTMLElement>(`[data-tab="${active}"]`);
    if (!rail || !tab) return;
    const { left, right } = tab.getBoundingClientRect();
    const box = rail.getBoundingClientRect();
    if (left < box.left || right > box.right) rail.scrollTo({ left: tab.offsetLeft - 24, behavior: "smooth" });
  }, [active]);

  if (items.length < 2) return null;

  return (
    <nav aria-label="On this page" className="sticky top-0 z-40 border-y border-border-soft bg-white/95 backdrop-blur-sm">
      <div className="page flex h-[60px] items-stretch gap-6">
        {label && (
          <span className="hidden shrink-0 items-center text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint lg:flex">
            {label}
          </span>
        )}
        <div ref={railRef} className="rail flex min-w-0 flex-1 items-stretch gap-7 overflow-x-auto">
          {items.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              data-tab={item.id}
              aria-current={active === item.id ? "true" : undefined}
              className={clsx(
                "relative flex shrink-0 items-center whitespace-nowrap text-[14.5px] font-semibold transition-colors",
                active === item.id ? "text-accent-deep" : "text-ink-meta hover:text-ink",
              )}
            >
              {item.label}
              <span
                className={clsx(
                  "absolute inset-x-0 bottom-[-1px] h-[3px] rounded-t-sm bg-accent transition-opacity",
                  active === item.id ? "opacity-100" : "opacity-0",
                )}
              />
            </a>
          ))}
        </div>
        {action && (
          <a
            href={action.href}
            className={clsx(
              "my-auto hidden shrink-0 items-center gap-2 text-[14.5px] font-bold sm:flex",
              action.filled
                ? "rounded-[5px] bg-accent-deep px-4 py-2.5 text-white hover:bg-accent"
                : "text-accent-deep hover:underline",
            )}
          >
            <Icon name="chat" size={17} strokeWidth={1.9} />
            {action.label}
          </a>
        )}
      </div>
    </nav>
  );
}
