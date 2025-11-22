import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { telemetryService } from '@/services/telemetryService'

export interface ResourceQueryConfig<T> {
  endpoint: string
  queryKey: string
  dataExtractor: (response: any) => unknown[]
  filter?: (item: Record<string, unknown>) => boolean
  mapper: (item: Record<string, unknown>) => T
  staleTime?: number
  enabledCheck?: (teamFilter?: string | string[]) => boolean
}

export const createResourceQuery =
  <T>(config: ResourceQueryConfig<T>) =>
  (teamFilter?: string | string[], enabled = true) => {
    return useQuery<T[]>({
      queryKey: [config.queryKey, teamFilter],
      queryFn: async () => {
        const startTime = performance.now()

        // Track query attempt
        telemetryService.trackEvent('data.query_start', {
          'query.resource_type': config.queryKey,
          'query.endpoint': config.endpoint,
          'query.has_team_filter': !!teamFilter,
          'query.team_filter_type': Array.isArray(teamFilter) ? 'multiple' : 'single',
          'query.enabled': enabled
        })

        try {
          // Check if query should be disabled based on config
          if (config.enabledCheck && !config.enabledCheck(teamFilter)) {
            telemetryService.trackEvent('data.query_disabled', {
              'query.resource_type': config.queryKey,
              'query.reason': 'enabledCheck_failed'
            })
            return []
          }

          // Build params based on teamFilter
          const params = teamFilter ? {
            teamName: Array.isArray(teamFilter) ? teamFilter.join(',') : teamFilter
          } : {}

          const response = await apiClient.get(config.endpoint, params)
          const data = config.dataExtractor(response)
          const items = Array.isArray(data) ? data : []

          const rows = items as Record<string, unknown>[]
          const filterFn = config.filter || (() => true)
          const filteredItems = rows.filter((item) => filterFn(item)).map((item) => config.mapper(item))

          const duration = performance.now() - startTime

          // Track successful query
          telemetryService.trackEvent('data.query_success', {
            'query.resource_type': config.queryKey,
            'query.endpoint': config.endpoint,
            'query.duration_ms': duration,
            'query.result_count': filteredItems.length,
            'query.raw_count': items.length,
            'query.has_filter': !!(config.filter),
            'query.cache_enabled': !!(config.staleTime)
          })

          return filteredItems
        } catch (error) {
          const duration = performance.now() - startTime

          // Track query failure
          telemetryService.trackEvent('data.query_error', {
            'query.resource_type': config.queryKey,
            'query.endpoint': config.endpoint,
            'query.duration_ms': duration,
            'query.error': (error as Error).message || 'unknown_error'
          })

          throw error
        }
      },
      enabled: enabled && (!config.enabledCheck || config.enabledCheck(teamFilter)),
      staleTime: config.staleTime || 30 * 1000,
      meta: {
        // Add telemetry meta for React Query devtools
        telemetry: {
          resourceType: config.queryKey,
          endpoint: config.endpoint
        }
      }
    })
  }
