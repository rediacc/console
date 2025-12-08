import { useCallback, useEffect, useRef, useState } from 'react';

type DebouncedCallback = {
  (): void;
  cancel: () => void;
};

const createDebouncedCallback = (callback: () => void, delay = 300): DebouncedCallback => {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  const debounced = () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    timeoutId = setTimeout(() => {
      callback();
    }, delay);
  };

  debounced.cancel = () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };

  return debounced;
};

interface UseDynamicPageSizeOptions {
  rowHeight?: number; // Default row height in pixels
  headerHeight?: number; // Table header height
  paginationHeight?: number; // Pagination controls height
  containerOffset?: number; // Additional offset for container padding/margins
  minRows?: number; // Minimum rows to show
  maxRows?: number; // Maximum rows to show
}

export const useDynamicPageSize = (
  tableContainerRef: React.RefObject<HTMLDivElement | null>,
  options: UseDynamicPageSizeOptions = {}
) => {
  const {
    rowHeight = 54, // Ant Design default row height
    headerHeight = 55, // Ant Design table header height
    paginationHeight = 64, // Ant Design pagination height
    containerOffset = 32, // Additional padding/margins
    minRows = 5,
    maxRows = 100,
  } = options;

  const [pageSize, setPageSize] = useState(10); // Default page size
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  const calculatePageSize = useCallback(() => {
    if (!tableContainerRef.current) return;

    // Get the container height
    const containerHeight = tableContainerRef.current.offsetHeight;

    // Calculate available height for rows
    const availableHeight = containerHeight - headerHeight - paginationHeight - containerOffset;

    // Calculate how many rows can fit
    const calculatedRows = Math.floor(availableHeight / rowHeight);

    // Apply min/max constraints
    const newPageSize = Math.max(minRows, Math.min(maxRows, calculatedRows));

    setPageSize(newPageSize);
  }, [
    tableContainerRef,
    rowHeight,
    headerHeight,
    paginationHeight,
    containerOffset,
    minRows,
    maxRows,
  ]);

  // Store debounced function in a ref to avoid recreating it
  const debouncedCalculatePageSizeRef = useRef<DebouncedCallback | null>(null);

  // Create debounced function only once or when calculatePageSize changes
  useEffect(() => {
    debouncedCalculatePageSizeRef.current = createDebouncedCallback(calculatePageSize, 300);
    return () => {
      debouncedCalculatePageSizeRef.current?.cancel();
    };
  }, [calculatePageSize]);

  useEffect(() => {
    // Initial calculation
    calculatePageSize();

    // Set up ResizeObserver for the container
    if (tableContainerRef.current && window.ResizeObserver) {
      resizeObserverRef.current = new ResizeObserver(() => {
        debouncedCalculatePageSizeRef.current?.();
      });
      resizeObserverRef.current.observe(tableContainerRef.current);
    }

    // Cleanup
    return () => {
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
      }
      debouncedCalculatePageSizeRef.current?.cancel();
    };
  }, [calculatePageSize, tableContainerRef]);

  return pageSize;
};
