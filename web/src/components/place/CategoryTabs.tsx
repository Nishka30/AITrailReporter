"use client";

import { useState } from "react";
import clsx from "clsx";
import type { Tab } from "@/lib/content/locationPage";

export interface TabbedItem {
  id: string;
  /** Tab keys this item appears under ("All" always includes it). */
  keys: string[];
  node: React.ReactNode;
}

const ALL = "__all__";

/**
 * Category filter row + the cards it filters -- the reference guide's
 * "All local updates | Getting here | Stays & services" pattern. Cards are
 * rendered on the server and handed in as nodes; this component only
 * decides which are visible. Tabs come from real category data (see
 * locationPage.ts reportTabs/placeTabs), never a fixed list.
 */
export function CategoryTabs({
  tabs,
  items,
  allLabel,
  initialKey = null,
  emptyMessages = {},
  defaultEmptyMessage,
  gridClassName = "grid gap-5 sm:grid-cols-2 lg:grid-cols-3",
}: {
  tabs: Tab[];
  items: TabbedItem[];
  allLabel: string;
  initialKey?: string | null;
  emptyMessages?: Record<string, string>;
  defaultEmptyMessage: string;
  gridClassName?: string;
}) {
  const [selected, setSelected] = useState<string>(
    initialKey && tabs.some((t) => t.key === initialKey) ? initialKey : ALL,
  );
  const visible = selected === ALL ? items : items.filter((item) => item.keys.includes(selected));
  const options = [{ key: ALL, label: allLabel, count: items.length }, ...tabs];

  return (
    <div>
      {tabs.length > 0 && (
        <div role="tablist" aria-label="Filter by category" className="rail -mx-5 mb-6 flex gap-2 overflow-x-auto px-5 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
          {options.map((tab) => {
            const active = tab.key === selected;
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setSelected(tab.key)}
                className={clsx(
                  "flex min-h-[38px] shrink-0 items-center gap-2 rounded-full border px-4 text-[13px] font-semibold transition",
                  active
                    ? "border-ink bg-ink text-paper"
                    : "border-border bg-paper-elevated text-ink-soft hover:border-border-strong hover:text-ink",
                )}
              >
                {tab.label}
                <span className={clsx("text-xs font-medium", active ? "text-paper/60" : "text-ink-faint")}>{tab.count}</span>
              </button>
            );
          })}
        </div>
      )}

      {visible.length > 0 ? (
        <div className={gridClassName}>
          {visible.map((item) => (
            <div key={item.id} className="flex">
              {item.node}
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-xl border border-dashed border-border-strong bg-paper-elevated px-5 py-6 text-sm text-ink-soft">
          {emptyMessages[selected] ?? defaultEmptyMessage}
        </p>
      )}
    </div>
  );
}
