import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

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
        // Check if query should be disabled based on config
        if (config.enabledCheck && !config.enabledCheck(teamFilter)) {
          return []
        }

        // Build params based on teamFilter
        const params = teamFilter ? {
          teamName: Array.isArray(teamFilter) ? teamFilter.join(',') : teamFilter
        } : {}
        
        const response = await apiClient.get(config.endpoint, params)
        const data = config.dataExtractor(response)
        const items = Array.isArray(data) ? data : []
        
        return items
          .filter(config.filter || (() => true))
          .map(config.mapper)
      },
      enabled: enabled && (!config.enabledCheck || config.enabledCheck(teamFilter)),
      staleTime: config.staleTime || 30 * 1000, // 30 seconds default
    })
  }

// Common data extractors
export const dataExtractors = {
  primaryOrSecondary: (response: any) => response.tables?.[1]?.data || response.tables?.[0]?.data || [],
  primary: (response: any) => response.tables?.[0]?.data || []
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