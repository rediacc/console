import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { telemetryService } from '@/services/telemetryService'

export interface ResourceQueryConfig<T> {
  endpoint: string
  queryKey: string
  dataExtractor: (response: any) => T[]
  filter?: (item: any) => boolean
  mapper: (item: any) => T
  staleTime?: number
  enabledCheck?: (teamFilter?: string | string[]) => boolean
}

export const createResourceQuery = <T>(config: ResourceQueryConfig<T>) =>
  (teamFilter?: string | string[], enabled: boolean = true) => {
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

          const filteredItems = items
            .filter(config.filter || (() => true))
            .map(config.mapper)

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
      staleTime: config.staleTime || 30 * 1000, // 30 seconds default
      meta: {
        // Add telemetry meta for React Query devtools
        telemetry: {
          resourceType: config.queryKey,
          endpoint: config.endpoint
        }
      }
    })
  }

// Common data extractors
export const dataExtractors = {
  primaryOrSecondary: (response: any) => response.resultSets?.[1]?.data || [],
  primary: (response: any) => response.resultSets?.[0]?.data || []
}

// Common filters
export const filters = {
  hasName: (nameField: string) => (item: any) => item && item[nameField],
  isValid: (item: any) => !!item
}

// Field mappers
export const createFieldMapper = <T>(fieldMap: Record<string, string | ((item: any) => any)>) => 
  (item: any): T => {
    const result = {} as T
    Object.entries(fieldMap).forEach(([key, value]) => {
      if (typeof value === 'function') {
        result[key as keyof T] = value(item)
      } else {
        result[key as keyof T] = item[value] || (key.includes('vault') ? '{}' : key.includes('Version') ? 1 : key.includes('Count') ? 0 : undefined)
      }
    })
    return result
  }