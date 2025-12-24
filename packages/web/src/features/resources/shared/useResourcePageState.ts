import { useCallback, useEffect, useRef, useState } from 'react';

export const useResourcePageState = <T>(
  onRefresh: () => Promise<void> | void,
  shouldAutoRefresh: boolean
) => {
  const [selectedResource, setSelectedResource] = useState<T | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const hasInitiallyLoadedRef = useRef(false);

  const handleRefresh = useCallback(async () => {
    setRefreshKey((prev) => prev + 1);
    await onRefresh();
  }, [onRefresh]);

  useEffect(() => {
    if (!shouldAutoRefresh || hasInitiallyLoadedRef.current) {
      return;
    }

    hasInitiallyLoadedRef.current = true;
    const timer = setTimeout(() => {
      void handleRefresh();
    }, 0);

    return () => {
      clearTimeout(timer);
    };
  }, [shouldAutoRefresh, handleRefresh]);

  const handlePanelClose = useCallback(() => {
    setSelectedResource(null);
  }, []);

  return {
    selectedResource,
    setSelectedResource,
    refreshKey,
    handleRefresh,
    handlePanelClose,
  };
};
