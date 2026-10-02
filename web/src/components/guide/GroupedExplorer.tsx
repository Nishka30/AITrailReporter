"use client";

import { useState } from "react";
import { FilterPills } from "./FilterGrid";

export interface ExplorerGroup {
  key: string;
  label: string;
  count: number;
  /** A one-place group renders as a single wide feature row. */
  content: React.ReactNode;
}

/**
 * "Explore {place} and the nearby trail": pills select a group; each group
 * is a labelled subsection ("Lodging · 5 local picks") over its cards.
 */
export function GroupedExplorer({ groups, allLabel }: { groups: ExplorerGroup[]; allLabel: string }) {
  const [selected, setSelected] = useState("__all__");
  const visible = selected === "__all__" ? groups : groups.filter((g) => g.key === selected);

  return (
    <div>
      {groups.length > 1 && (
        <FilterPills tabs={groups.map((g) => ({ key: g.key, label: g.label }))} selected={selected} onSelect={setSelected} allLabel={allLabel} />
      )}
      <div className="space-y-12">
        {visible.map((g) => (
          <div key={g.key}>
            <div className="mb-6 flex items-end justify-between gap-4 border-b border-border-soft pb-4">
              <h3 className="text-[22px] font-bold tracking-[-0.02em] text-ink">{g.label}</h3>
              <span className="text-[13px] text-ink-faint">
                {g.count} local pick{g.count === 1 ? "" : "s"}
              </span>
            </div>
            {g.content}
          </div>
        ))}
      </div>
    </div>
  );
}
