import { useState, useEffect, useCallback, useRef } from 'react';
import { debounce } from 'lodash';

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
  }, [tableContainerRef, rowHeight, headerHeight, paginationHeight, containerOffset, minRows, maxRows]);

  // Store debounced function in a ref to avoid recreating it
  const debouncedCalculatePageSizeRef = useRef<ReturnType<typeof debounce> | null>(null);

  // Create debounced function only once or when calculatePageSize changes
  useEffect(() => {
    debouncedCalculatePageSizeRef.current = debounce(calculatePageSize, 300);
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

    // Also listen to window resize as a fallback
    const handleResize = () => {
      debouncedCalculatePageSizeRef.current?.();
    };
    window.addEventListener('resize', handleResize);

    // Cleanup
    return () => {
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
      }
      window.removeEventListener('resize', handleResize);
      debouncedCalculatePageSizeRef.current?.cancel();
    };
  }, [calculatePageSize, tableContainerRef]);

  return pageSize;
};