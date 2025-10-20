import { useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
import { minifyJSON } from '@/utils/json'
import { telemetryService } from '@/services/telemetryService'

export interface MutationConfig<T> {
  endpoint: string
  method?: 'post' | 'put' | 'delete'
  invalidateKeys: string[] | ((variables: T) => string[])
  successMessage: (variables: T) => string
  errorMessage?: string
  transformData?: (data: T) => any | Promise<any>
}

export const createMutation = <T>(config: MutationConfig<T>) => () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: T) => {
      const startTime = performance.now()
      const method = config.method || 'post'

      // Track mutation attempt
      telemetryService.trackEvent('data.mutation_start', {
        'mutation.endpoint': config.endpoint,
        'mutation.method': method,
        'mutation.has_transform': !!(config.transformData),
        'mutation.data_size': JSON.stringify(data).length
      })

      try {
        const transformedData = config.transformData ? await config.transformData(data) : data
        const response = await apiClient[method](config.endpoint, transformedData)

        const duration = performance.now() - startTime

        // Track successful mutation
        telemetryService.trackEvent('data.mutation_success', {
          'mutation.endpoint': config.endpoint,
          'mutation.method': method,
          'mutation.duration_ms': duration,
          'mutation.response_status': response.status || 200,
          'mutation.invalidated_keys_count': Array.isArray(config.invalidateKeys)
            ? config.invalidateKeys.length
            : 1
        })

        return response
      } catch (error) {
        const duration = performance.now() - startTime

        // Track mutation failure
        telemetryService.trackEvent('data.mutation_error', {
          'mutation.endpoint': config.endpoint,
          'mutation.method': method,
          'mutation.duration_ms': duration,
          'mutation.error': (error as Error).message || 'unknown_error',
          'mutation.error_type': (error as any)?.response?.status || 'network_error'
        })

        throw error
      }
    },
    onSuccess: (_, variables) => {
      // Track cache invalidation
      const keys = typeof config.invalidateKeys === 'function'
        ? config.invalidateKeys(variables)
        : config.invalidateKeys

      telemetryService.trackEvent('data.cache_invalidation', {
        'cache.invalidated_keys': keys.join(','),
        'cache.key_count': keys.length,
        'cache.endpoint': config.endpoint
      })

      keys.forEach(key => queryClient.invalidateQueries({ queryKey: [key] }))
      showMessage('success', config.successMessage(variables))
    },
    onError: (error: any) => {
      showMessage('error', error.message || config.errorMessage || 'Operation failed')
    },
    meta: {
      // Add telemetry meta for React Query devtools
      telemetry: {
        endpoint: config.endpoint,
        method: config.method || 'post'
      }
    }
  })
}

export const createResourceMutation = <T extends Record<string, any>>(
  resourceType: string,
  operation: 'create' | 'update' | 'delete',
  endpoint: string,
  nameField: keyof T,
  additionalKeys: string[] = []
) => {
  const baseMutation = createMutation<T>({
    endpoint,
    method: ({ create: 'post', update: 'put', delete: 'delete' } as const)[operation],
    invalidateKeys: [resourceType.toLowerCase() + 's', 'dropdown-data', ...additionalKeys],
    successMessage: (variables: T) => {
      const name = variables[nameField] as string
      const actions = { create: 'created', update: 'updated', delete: 'deleted' }
      return `${resourceType} "${name}" ${actions[operation]} successfully`
    },
    errorMessage: `Failed to ${operation} ${resourceType.toLowerCase()}`,
  })

  // Return enhanced version with business-level telemetry
  return () => {
    const mutation = baseMutation()

    // Wrap the original mutate function to add business telemetry
    const originalMutate = mutation.mutate
    mutation.mutate = (variables: T, options?: any) => {
      // Track business-level resource operation
      telemetryService.trackEvent('business.resource_operation', {
        'resource.type': resourceType.toLowerCase(),
        'resource.operation': operation,
        'resource.name': variables[nameField] as string || 'unknown',
        'resource.has_vault': Object.keys(variables).some(key => key.toLowerCase().includes('vault')),
        'resource.field_count': Object.keys(variables).length
      })

      return originalMutate(variables, {
        ...options,
        onSuccess: (data: any, vars: T, context: any) => {
          // Track successful business operation
          telemetryService.trackEvent('business.resource_operation_success', {
            'resource.type': resourceType.toLowerCase(),
            'resource.operation': operation,
            'resource.name': vars[nameField] as string || 'unknown'
          })

          options?.onSuccess?.(data, vars, context)
        },
        onError: (error: any, vars: T, context: any) => {
          // Track failed business operation
          telemetryService.trackEvent('business.resource_operation_error', {
            'resource.type': resourceType.toLowerCase(),
            'resource.operation': operation,
            'resource.name': vars[nameField] as string || 'unknown',
            'resource.error': error.message || 'unknown_error'
          })

          options?.onError?.(error, vars, context)
        }
      })
    }

    return mutation
  }
}

export const createVaultUpdateMutation = <T extends Record<string, any>>(
  resourceType: string,
  endpoint: string,
  nameField: keyof T,
  vaultField: keyof T
) => createMutation<T>({
  endpoint,
  method: 'put',
  invalidateKeys: [resourceType.toLowerCase() + 's'],
  successMessage: (variables) => `${resourceType} vault updated for "${variables[nameField]}"`,
  errorMessage: `Failed to update ${resourceType.toLowerCase()} vault`,
  transformData: (data) => ({
    ...data,
    [vaultField]: minifyJSON(data[vaultField] as string)
  })
})