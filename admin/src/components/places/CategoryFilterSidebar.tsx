import { ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

import type { PlaceCategoryGroupOptions } from '../../api/types';

const INITIAL_VISIBLE_OPTIONS = 6;

/**
 * The Places filter sidebar: TrailMind's own category catalog
 * (backend/app/services/places/category_catalog.py), grouped into a handful
 * of user-friendly sections by backend/app/services/places/category_ui_groups.py.
 * Nothing here invents a category -- `groups` comes straight from
 * GET /api/v1/admin/places/categories, so every label, count and grouping is
 * real, current database data.
 */
export default function CategoryFilterSidebar({
  groups,
  selectedCategories,
  selectedGroups,
  onToggleCategory,
  onToggleGroup,
  onClearAll,
}: {
  groups: PlaceCategoryGroupOptions[];
  selectedCategories: string[];
  selectedGroups: string[];
  onToggleCategory: (slug: string) => void;
  onToggleGroup: (key: string) => void;
  onClearAll: () => void;
}) {
  const hasActiveFilter = selectedCategories.length > 0 || selectedGroups.length > 0;

  return (
    <div className="w-full shrink-0 space-y-1 lg:w-64">
      <button
        onClick={onClearAll}
        className={`mb-2 w-full rounded-lg px-3 py-2 text-left text-sm font-bold transition-colors ${
          !hasActiveFilter ? 'bg-ink text-marigold-soft' : 'text-ink-soft hover:bg-paper-muted'
        }`}
      >
        All Locations
      </button>

      {groups.map((group) => (
        <CategoryGroupSection
          key={group.key}
          group={group}
          groupSelected={selectedGroups.includes(group.key)}
          selectedCategories={selectedCategories}
          onToggleCategory={onToggleCategory}
          onToggleGroup={onToggleGroup}
        />
      ))}
    </div>
  );
}

function CategoryGroupSection({
  group,
  groupSelected,
  selectedCategories,
  onToggleCategory,
  onToggleGroup,
}: {
  group: PlaceCategoryGroupOptions;
  groupSelected: boolean;
  selectedCategories: string[];
  onToggleCategory: (slug: string) => void;
  onToggleGroup: (key: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const hasMore = group.options.length > INITIAL_VISIBLE_OPTIONS;
  const visibleOptions = expanded ? group.options : group.options.slice(0, INITIAL_VISIBLE_OPTIONS);

  return (
    <div className="border-b border-border pb-2 last:border-b-0">
      <button
        onClick={() => onToggleGroup(group.key)}
        className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm font-bold transition-colors ${
          groupSelected ? 'bg-ink text-marigold-soft' : 'text-ink hover:bg-paper-muted'
        }`}
      >
        <span>{group.label}</span>
        <span className={`text-xs font-bold ${groupSelected ? 'text-marigold-soft' : 'text-ink-faint'}`}>
          {group.count}
        </span>
      </button>

      <div className="mt-0.5 space-y-0.5 pl-2">
        {visibleOptions.map((option) => {
          const active = selectedCategories.includes(option.slug);
          return (
            <button
              key={option.slug}
              onClick={() => onToggleCategory(option.slug)}
              className={`flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-left text-sm transition-colors ${
                active ? 'bg-marigold-soft font-bold text-marigold-deep' : 'text-ink-soft hover:bg-paper-muted'
              }`}
            >
              <span>{option.display_name}</span>
              <span className="text-xs text-ink-faint">{option.count}</span>
            </button>
          );
        })}

        {hasMore ? (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex w-full items-center gap-1 rounded-lg px-3 py-1.5 text-left text-xs font-bold text-info hover:underline"
          >
            {expanded ? (
              <>
                <ChevronUp className="h-3 w-3" /> Show less
              </>
            ) : (
              <>
                <ChevronDown className="h-3 w-3" /> Show more ({group.options.length - INITIAL_VISIBLE_OPTIONS})
              </>
            )}
          </button>
        ) : null}
      </div>
    </div>
  );
}
