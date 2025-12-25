import { useQuery } from '@tanstack/react-query';
import { telemetryService } from '@/services/telemetryService';

export interface ResourceQueryConfig<T> {
  queryKey: string;
  fetcher: (teamFilter?: string | string[]) => Promise<T[]>;
  staleTime?: number;
  enabledCheck?: (teamFilter?: string | string[]) => boolean;
  operationName?: string;
}

export const createResourceQuery =
  <T>(config: ResourceQueryConfig<T>) =>
  (teamFilter?: string | string[], enabled = true) => {
    return useQuery<T[]>({
      queryKey: [config.queryKey, teamFilter],
      queryFn: async () => {
        const startTime = performance.now();
        const operationName = config.operationName ?? config.queryKey;

        telemetryService.trackEvent('data.query_start', {
          'query.resource_type': config.queryKey,
          'query.operation': operationName,
          'query.has_team_filter': !!teamFilter,
          'query.team_filter_type': Array.isArray(teamFilter) ? 'multiple' : 'single',
          'query.enabled': enabled,
        });

        try {
          if (config.enabledCheck && !config.enabledCheck(teamFilter)) {
            telemetryService.trackEvent('data.query_disabled', {
              'query.resource_type': config.queryKey,
              'query.reason': 'enabledCheck_failed',
            });
            return [];
          }

          const data = await config.fetcher(teamFilter);
          const duration = performance.now() - startTime;

          telemetryService.trackEvent('data.query_success', {
            'query.resource_type': config.queryKey,
            'query.operation': operationName,
            'query.duration_ms': duration,
            'query.result_count': data.length,
            'query.cache_enabled': Boolean(config.staleTime),
          });

          return data;
        } catch (error) {
          const duration = performance.now() - startTime;
          telemetryService.trackEvent('data.query_error', {
            'query.resource_type': config.queryKey,
            'query.operation': operationName,
            'query.duration_ms': duration,
            'query.error': (error as Error).message || 'unknown_error',
          });
          throw error;
        }
      },
      enabled: enabled && (!config.enabledCheck || config.enabledCheck(teamFilter)),
      staleTime: config.staleTime ?? 30 * 1000,
      meta: {
        telemetry: {
          resourceType: config.queryKey,
          operation: config.operationName ?? config.queryKey,
        },
      },
    });
  };
