import { useState, useCallback, useMemo } from 'react';

/**
 * Options for useFilters hook
 */
export interface UseFiltersOptions<T extends Record<string, unknown>> {
  /** Callback when filters change */
  onFilterChange?: (filters: T) => void;
}

/**
 * Return type for useFilters hook
 */
export interface UseFiltersReturn<T extends Record<string, unknown>> {
  /** Current filter values */
  filters: T;
  /** Set a single filter value */
  setFilter: <K extends keyof T>(key: K, value: T[K]) => void;
  /** Set multiple filter values */
  setFilters: (filters: T | ((prev: T) => T)) => void;
  /** Clear a single filter to its initial value */
  clearFilter: (key: keyof T) => void;
  /** Clear all filters to initial values */
  clearAllFilters: () => void;
  /** Check if any filters are active (different from initial) */
  hasActiveFilters: (ignoreKeys?: (keyof T)[]) => boolean;
  /** Get only the active (changed) filters */
  getActiveFilters: () => Partial<T>;
  /** Get count of active filters */
  activeFilterCount: number;
}

/**
 * Hook for managing filter state in list/table pages
 *
 * @example
 * interface QueueFilters {
 *   teamName: string
 *   status: string[]
 *   dateRange: [Dayjs | null, Dayjs | null] | null
 *   onlyStale: boolean
 * }
 *
 * const { filters, setFilter, clearAllFilters, hasActiveFilters } = useFilters<QueueFilters>({
 *   teamName: '',
 *   status: [],
 *   dateRange: null,
 *   onlyStale: false
 * })
 *
 * // Set individual filter
 * setFilter('teamName', 'Production')
 *
 * // Check if any filters are active
 * if (hasActiveFilters()) {
 *   // Show clear button
 * }
 *
 * // Clear all filters
 * clearAllFilters()
 */
export function useFilters<T extends Record<string, unknown>>(
  initialFilters: T,
  options?: UseFiltersOptions<T>
): UseFiltersReturn<T> {
  const [filters, setFiltersState] = useState<T>(initialFilters);

  const setFilter = useCallback(
    <K extends keyof T>(key: K, value: T[K]) => {
      setFiltersState((prev) => {
        const updated = { ...prev, [key]: value };
        options?.onFilterChange?.(updated);
        return updated;
      });
    },
    [options]
  );

  const setFilters = useCallback(
    (newFilters: T | ((prev: T) => T)) => {
      setFiltersState((prev) => {
        const updated = typeof newFilters === 'function' ? newFilters(prev) : newFilters;
        options?.onFilterChange?.(updated);
        return updated;
      });
    },
    [options]
  );

  const clearFilter = useCallback(
    (key: keyof T) => {
      setFiltersState((prev) => {
        const updated = { ...prev, [key]: initialFilters[key] };
        options?.onFilterChange?.(updated);
        return updated;
      });
    },
    [initialFilters, options]
  );

  const clearAllFilters = useCallback(() => {
    setFiltersState(initialFilters);
    options?.onFilterChange?.(initialFilters);
  }, [initialFilters, options]);

  const hasActiveFilters = useCallback(
    (ignoreKeys?: (keyof T)[]) => {
      const keysToCheck = (Object.keys(filters) as (keyof T)[]).filter(
        (k) => !ignoreKeys?.includes(k)
      );

      return keysToCheck.some((key) => {
        const currentValue = filters[key];
        const initialValue = initialFilters[key];

        // Handle null/undefined
        if (currentValue === null || currentValue === undefined) {
          return initialValue !== null && initialValue !== undefined;
        }

        // Handle arrays
        if (Array.isArray(currentValue)) {
          if (!Array.isArray(initialValue)) return true;
          if (currentValue.length !== initialValue.length) return true;
          return currentValue.some((v, i) => v !== initialValue[i]);
        }

        // Handle empty strings
        if (currentValue === '' && initialValue === '') {
          return false;
        }

        return currentValue !== initialValue;
      });
    },
    [filters, initialFilters]
  );

  const getActiveFilters = useCallback(() => {
    const active: Partial<T> = {};

    (Object.keys(filters) as (keyof T)[]).forEach((key) => {
      const currentValue = filters[key];
      const initialValue = initialFilters[key];

      let isActive = false;

      if (Array.isArray(currentValue)) {
        isActive =
          currentValue.length > 0 &&
          (!Array.isArray(initialValue) ||
            currentValue.length !== initialValue.length ||
            currentValue.some((v, i) => v !== initialValue[i]));
      } else if (currentValue !== null && currentValue !== undefined && currentValue !== '') {
        isActive = currentValue !== initialValue;
      }

      if (isActive) {
        active[key] = currentValue;
      }
    });

    return active;
  }, [filters, initialFilters]);

  const activeFilterCount = useMemo(() => {
    return Object.keys(getActiveFilters()).length;
  }, [getActiveFilters]);

  return {
    filters,
    setFilter,
    setFilters,
    clearFilter,
    clearAllFilters,
    hasActiveFilters,
    getActiveFilters,
    activeFilterCount,
  };
}

/**
 * Type helper for creating filter types
 */
export type FilterValue =
  | string
  | number
  | boolean
  | string[]
  | null
  | undefined
  | [unknown, unknown];
