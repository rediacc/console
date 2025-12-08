import { useCallback, useState } from 'react';

export interface UsePaginationOptions {
  defaultPageSize?: number;
  defaultPage?: number;
}

export interface UsePaginationReturn {
  page: number;
  pageSize: number;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  reset: () => void;
  onPageChange: (page: number, pageSize: number) => void;
}

export function usePagination(options: UsePaginationOptions = {}): UsePaginationReturn {
  const { defaultPageSize = 20, defaultPage = 1 } = options;

  const [page, setPage] = useState(defaultPage);
  const [pageSize, setPageSize] = useState(defaultPageSize);

  const reset = useCallback(() => {
    setPage(defaultPage);
  }, [defaultPage]);

  const handlePageSizeChange = useCallback(
    (size: number) => {
      setPageSize(size);
      setPage(defaultPage); // Reset to first page when changing page size
    },
    [defaultPage]
  );

  const onPageChange = useCallback(
    (newPage: number, newPageSize: number) => {
      setPage(newPage);
      if (newPageSize !== pageSize) {
        setPageSize(newPageSize);
      }
    },
    [pageSize]
  );

  return {
    page,
    pageSize,
    setPage,
    setPageSize: handlePageSizeChange,
    reset,
    onPageChange,
  };
}

/**
 * Create multiple pagination states for different sections
 * Useful for pages with multiple tables (e.g., QueuePage with active/completed/failed)
 */
export function useMultiPagination<T extends string>(
  sections: T[],
  defaultPageSize = 20
): Record<T, UsePaginationReturn> {
  const paginationStates = {} as Record<T, UsePaginationReturn>;

  sections.forEach((section) => {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    paginationStates[section] = usePagination({ defaultPageSize });
  });

  return paginationStates;
}
