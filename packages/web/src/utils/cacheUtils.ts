import { QueryClient } from '@tanstack/react-query';
import { QUERY_KEYS } from '@/api/queryKeys';

/**
 * Cache invalidation helpers for common patterns
 * These helpers reduce boilerplate by encapsulating repeated queryClient.invalidateQueries() calls
 * Now powered by centralized QUERY_KEYS for consistency
 */

/**
 * Invalidate all queue-related caches including bridge queries without specific bridge name
 * @param queryClient - The React Query client instance
 */
export const invalidateAllQueueCaches = (queryClient: QueryClient) => {
  void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
  void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.itemsByBridge('') });
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
  keys.forEach((key) => {
    void queryClient.invalidateQueries({ queryKey: key });
  });
};
