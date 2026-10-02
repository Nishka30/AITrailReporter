"use client";

import { useState } from "react";
import clsx from "clsx";
import { Icon } from "./Icons";

export interface FilterTab {
  key: string;
  label: string;
}

export interface FilterItem {
  id: string;
  keys: string[];
  node: React.ReactNode;
}

const ALL = "__all__";

export function FilterPills({
  tabs,
  selected,
  onSelect,
  allLabel,
  trailing,
}: {
  tabs: FilterTab[];
  selected: string;
  onSelect: (key: string) => void;
  allLabel: string;
  trailing?: React.ReactNode;
}) {
  const options = [{ key: ALL, label: allLabel }, ...tabs];
  return (
    <div className="mb-7 flex items-center gap-6">
      <div role="tablist" className="rail -mx-5 flex min-w-0 flex-1 gap-2.5 overflow-x-auto px-5 sm:mx-0 sm:flex-wrap sm:px-0">
        {options.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={tab.key === selected}
            onClick={() => onSelect(tab.key)}
            className={clsx(
              "h-[44px] shrink-0 rounded-[22px] border px-[17px] text-[14px] transition",
              tab.key === selected
                ? "border-pill bg-pill text-white"
                : "border-border-soft bg-white text-ink-meta hover:border-border-strong hover:text-ink",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {trailing && <div className="hidden shrink-0 text-[13px] text-ink-faint md:block">{trailing}</div>}
    </div>
  );
}

/**
 * Category pills over a card grid (the reference's "All local updates |
 * Getting here | Stays & services"), showing the newest few and letting the
 * reader include older checks. Cards render on the server; this only
 * decides which are visible.
 */
export function FilterGrid({
  tabs,
  items,
  allLabel,
  initialVisible = 6,
  trailing,
  footnote,
  moreLabel = "Include older local checks",
  emptyMessage,
  gridClassName = "grid gap-6 md:grid-cols-2 lg:grid-cols-3",
}: {
  tabs: FilterTab[];
  items: FilterItem[];
  allLabel: string;
  initialVisible?: number;
  trailing?: React.ReactNode;
  /** Rendered as "{shown} of {total} {footnote}". */
  footnote?: string;
  moreLabel?: string;
  emptyMessage: string;
  gridClassName?: string;
}) {
  const [selected, setSelected] = useState(ALL);
  const [expanded, setExpanded] = useState(false);
  const matching = selected === ALL ? items : items.filter((i) => i.keys.includes(selected));
  const shown = expanded ? matching : matching.slice(0, initialVisible);

  return (
    <div>
      {tabs.length > 0 && (
        <FilterPills
          tabs={tabs}
          selected={selected}
          onSelect={(k) => {
            setSelected(k);
            setExpanded(false);
          }}
          allLabel={allLabel}
          trailing={trailing}
        />
      )}
      {shown.length > 0 ? (
        <div className={gridClassName}>
          {shown.map((item) => (
            <div key={item.id} className="flex">
              {item.node}
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-[8px] border border-dashed border-border-strong px-6 py-8 text-[15px] text-ink-soft">{emptyMessage}</p>
      )}
      {(footnote || matching.length > shown.length) && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 text-[13px] text-ink-faint">
          <span>{footnote && `${shown.length} of ${matching.length} ${footnote}`}</span>
          {matching.length > shown.length && (
            <button
              type="button"
              onClick={() => setExpanded(true)}
              className="flex items-center gap-1.5 font-semibold text-accent-deep hover:underline"
            >
              {moreLabel}
              <Icon name="chevronDown" size={15} strokeWidth={2} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
