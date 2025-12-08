/**
 * Shared type definitions for custom hooks.
 * Use these to ensure consistent hook return signatures across the codebase.
 */

import type { FormInstance } from 'antd';

/**
 * Standard return type for modal state hooks
 */
export interface UseModalReturn<T = void> {
  /** Whether the modal is currently open */
  isOpen: boolean;
  /** Function to open the modal, optionally with data */
  open: (data?: T) => void;
  /** Function to close the modal */
  close: () => void;
  /** Current data passed to the modal */
  data: T | null;
}

/**
 * Standard return type for dialog state hooks (alias for modal)
 */
export type UseDialogReturn<T = void> = UseModalReturn<T>;

/**
 * Return type for form hooks
 */
export interface UseFormReturn<T extends Record<string, unknown> = Record<string, unknown>> {
  /** Ant Design form instance */
  form: FormInstance<T>;
  /** Whether the form is currently submitting */
  isSubmitting: boolean;
  /** Function to submit the form */
  submit: () => Promise<void>;
  /** Function to reset the form */
  reset: () => void;
  /** Whether the form has been modified */
  isDirty: boolean;
}

/**
 * Return type for pagination hooks
 */
export interface UsePaginationReturn {
  /** Current page number (1-indexed) */
  currentPage: number;
  /** Items per page */
  pageSize: number;
  /** Total number of items */
  total: number;
  /** Function to change page */
  setPage: (page: number) => void;
  /** Function to change page size */
  setPageSize: (size: number) => void;
  /** Whether there is a next page */
  hasNextPage: boolean;
  /** Whether there is a previous page */
  hasPrevPage: boolean;
}

/**
 * Return type for filter hooks
 */
export interface UseFiltersReturn<T extends Record<string, unknown>> {
  /** Current filter values */
  filters: T;
  /** Function to update a single filter */
  setFilter: <K extends keyof T>(key: K, value: T[K]) => void;
  /** Function to update multiple filters */
  setFilters: (filters: Partial<T>) => void;
  /** Function to reset all filters */
  resetFilters: () => void;
  /** Whether any filters are active */
  hasActiveFilters: boolean;
}

/**
 * Return type for selection hooks
 */
export interface UseSelectionReturn<T> {
  /** Currently selected items */
  selectedItems: T[];
  /** Currently selected keys (for table row selection) */
  selectedKeys: React.Key[];
  /** Function to select items */
  select: (items: T[]) => void;
  /** Function to toggle an item's selection */
  toggle: (item: T) => void;
  /** Function to clear selection */
  clear: () => void;
  /** Function to select all */
  selectAll: (items: T[]) => void;
  /** Whether a specific item is selected */
  isSelected: (item: T) => boolean;
}

/**
 * Return type for async operation hooks
 */
export interface UseAsyncReturn<T, E = Error> {
  /** The data returned from the async operation */
  data: T | null;
  /** Whether the operation is in progress */
  loading: boolean;
  /** Any error that occurred */
  error: E | null;
  /** Function to trigger the async operation */
  execute: (...args: unknown[]) => Promise<T>;
  /** Function to reset the state */
  reset: () => void;
}
