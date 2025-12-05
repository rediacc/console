import { QueryClient } from '@tanstack/react-query';
import { QUERY_KEYS } from '@/api/queryKeys';

/**
 * Cache invalidation helpers for common patterns
 * These helpers reduce boilerplate by encapsulating repeated queryClient.invalidateQueries() calls
 * Now powered by centralized QUERY_KEYS for consistency
 */

/**
 * Invalidate queue-related caches
 * @param queryClient - The React Query client instance
 * @param bridgeName - Optional bridge name to invalidate bridge-specific queue caches
 */
export const invalidateQueueCaches = (
  queryClient: QueryClient,
  bridgeName?: string
) => {
  queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
  if (bridgeName) {
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.itemsByBridge(bridgeName) });
  }
};

/**
 * Invalidate all queue-related caches including bridge queries without specific bridge name
 * @param queryClient - The React Query client instance
 */
export const invalidateAllQueueCaches = (queryClient: QueryClient) => {
  queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
  queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.itemsByBridge('') });
};

/**
 * Invalidate team-related caches
 * @param queryClient - The React Query client instance
 */
export const invalidateTeamCaches = (queryClient: QueryClient) => {
  queryClient.invalidateQueries({ queryKey: QUERY_KEYS.teams.all });
};

/**
 * Invalidate machine-related caches
 * @param queryClient - The React Query client instance
 */
export const invalidateMachineCaches = (queryClient: QueryClient) => {
  queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.machines.all] });
};

/**
 * Invalidate bridge-related caches
 * @param queryClient - The React Query client instance
 */
export const invalidateBridgeCaches = (queryClient: QueryClient) => {
  queryClient.invalidateQueries({ queryKey: QUERY_KEYS.bridges.list() });
};

/**
 * Invalidate dropdown data caches
 * @param queryClient - The React Query client instance
 */
export const invalidateDropdownCaches = (queryClient: QueryClient) => {
  queryClient.invalidateQueries({ queryKey: QUERY_KEYS.dropdown.data() });
};

/**
 * Generic invalidation helper for multiple query keys
 * @param queryClient - The React Query client instance
 * @param keys - Array of query keys to invalidate
 *
 * @example
 * invalidateQueries(queryClient, [['teams'], ['machines'], ['dropdown-data']])
 */
export const invalidateQueries = (
  queryClient: QueryClient,
  keys: readonly (readonly string[])[]
) => {
  keys.forEach(key => {
    queryClient.invalidateQueries({ queryKey: key });
  });
};
