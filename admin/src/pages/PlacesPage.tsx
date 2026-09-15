import { useQuery } from '@tanstack/react-query';
import { MapPin, Search, X } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import { getPlaceCategoryGroups, getPlaces } from '../api/admin';
import PageHeader from '../components/layout/PageHeader';
import CategoryFilterSidebar from '../components/places/CategoryFilterSidebar';
import PlaceCard from '../components/places/PlaceCard';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import Pagination from '../components/ui/Pagination';

const PAGE_SIZE = 15;

/** Splits/joins the comma-separated multi-select values the backend expects
 * (see PlaceQueueFilters.category/group) to/from a string[] for the UI. */
function parseList(value: string | null): string[] {
  return value ? value.split(',').filter(Boolean) : [];
}

export default function PlacesPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const q = searchParams.get('q') ?? '';
  const selectedCategories = parseList(searchParams.get('category'));
  const selectedGroups = parseList(searchParams.get('group'));
  const page = Number(searchParams.get('page') ?? '1');

  const filters = {
    q: q || undefined,
    category: selectedCategories.length ? selectedCategories.join(',') : undefined,
    group: selectedGroups.length ? selectedGroups.join(',') : undefined,
    page,
    page_size: PAGE_SIZE,
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin-places', filters],
    queryFn: () => getPlaces(filters),
  });

  const { data: categoryGroups } = useQuery({
    queryKey: ['admin-place-categories'],
    queryFn: getPlaceCategoryGroups,
    // The catalog/assignment counts change slowly (only when places are
    // discovered/reclassified) -- no need to refetch this on every filter
    // change the way the places list itself does.
    staleTime: 5 * 60 * 1000,
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== 'page') next.delete('page');
    setSearchParams(next);
  };

  const toggleInList = (key: 'category' | 'group', value: string) => {
    const current = key === 'category' ? selectedCategories : selectedGroups;
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    setParam(key, next.join(','));
  };

  const clearAllFilters = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('category');
    next.delete('group');
    next.delete('page');
    setSearchParams(next);
  };

  const hasActiveFilters = !!q || selectedCategories.length > 0 || selectedGroups.length > 0;

  return (
    <div>
      <PageHeader title="Places" description="Known places, and how much has been reported nearby." />

      <div className="flex flex-col gap-6 lg:flex-row">
        {categoryGroups && categoryGroups.length > 0 ? (
          <CategoryFilterSidebar
            groups={categoryGroups}
            selectedCategories={selectedCategories}
            selectedGroups={selectedGroups}
            onToggleCategory={(slug) => toggleInList('category', slug)}
            onToggleGroup={(key) => toggleInList('group', key)}
            onClearAll={clearAllFilters}
          />
        ) : null}

        <div className="min-w-0 flex-1">
          <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-paper-elevated p-3">
            <div className="flex items-center gap-2 rounded-lg border border-border bg-paper px-3 py-1.5">
              <Search className="h-4 w-4 text-ink-faint" />
              <input
                value={q}
                onChange={(e) => setParam('q', e.target.value)}
                placeholder="Search places by name…"
                className="w-56 bg-transparent text-sm outline-none"
              />
            </div>
            {hasActiveFilters ? (
              <button
                onClick={() => {
                  clearAllFilters();
                  setParam('q', '');
                }}
                className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-sm font-bold text-ink-soft hover:bg-paper-muted"
              >
                <X className="h-3.5 w-3.5" /> Clear filters
              </button>
            ) : null}
          </div>

          {isLoading ? <LoadingState /> : null}
          {isError ? <ErrorState message="Could not load places." onRetry={() => refetch()} /> : null}

          {data && data.items.length === 0 ? (
            <EmptyState
              title={hasActiveFilters ? 'No locations match these filters' : 'No known places yet'}
              description={
                hasActiveFilters ? 'Try a different search term or category, or clear filters.' : undefined
              }
              icon={<MapPin className="h-8 w-8" />}
            />
          ) : null}

          {data && data.items.length > 0 ? (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {data.items.map((place) => (
                  <PlaceCard key={place.location_id} place={place} />
                ))}
              </div>
              <Pagination
                page={data.page}
                pageSize={data.page_size}
                total={data.total}
                onPageChange={(p) => setParam('page', String(p))}
              />
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
