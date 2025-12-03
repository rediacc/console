import { useMutation, useQueryClient } from '@tanstack/react-query'
import { showMessage } from '@/utils/messages'
import { minifyJSON } from '@/utils/json'
import { telemetryService } from '@/services/telemetryService'

export interface MutationConfig<TVariables, TResult = unknown, TTransformed = TVariables> {
  request: (data: TTransformed) => Promise<TResult>
  invalidateKeys: string[] | ((variables: TVariables) => string[])
  successMessage: (variables: TVariables) => string
  errorMessage?: string
  transformData?: (data: TVariables) => TTransformed | Promise<TTransformed>
  operationName?: string
}

export const createMutation = <TVariables, TResult = unknown, TTransformed = TVariables>(
  config: MutationConfig<TVariables, TResult, TTransformed>
) => () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: TVariables) => {
      const startTime = performance.now()
      const operationName = config.operationName ?? 'mutation'

      telemetryService.trackEvent('data.mutation_start', {
        'mutation.operation': operationName,
        'mutation.has_transform': Boolean(config.transformData),
        'mutation.data_size': JSON.stringify(data).length,
      })

      try {
        const transformed = config.transformData
          ? await config.transformData(data)
          : (data as unknown as TTransformed)
        const response = await config.request(transformed)

        const duration = performance.now() - startTime
        telemetryService.trackEvent('data.mutation_success', {
          'mutation.operation': operationName,
          'mutation.duration_ms': duration,
          'mutation.response_status': 'success',
          'mutation.invalidated_keys_count': Array.isArray(config.invalidateKeys)
            ? config.invalidateKeys.length
            : 1,
        })

        return response
      } catch (error) {
        const duration = performance.now() - startTime
        telemetryService.trackEvent('data.mutation_error', {
          'mutation.operation': operationName,
          'mutation.duration_ms': duration,
          'mutation.error': (error as Error).message || 'unknown_error',
          'mutation.error_type': (error as any)?.response?.status || 'network_error',
        })
        throw error
      }
    },
    onSuccess: (_, variables) => {
      const keys = typeof config.invalidateKeys === 'function'
        ? config.invalidateKeys(variables)
        : config.invalidateKeys

      telemetryService.trackEvent('data.cache_invalidation', {
        'cache.invalidated_keys': keys.join(','),
        'cache.key_count': keys.length,
        'cache.operation': config.operationName ?? 'mutation',
      })

      keys.forEach(key => queryClient.invalidateQueries({ queryKey: [key] }))
      showMessage('success', config.successMessage(variables))
    },
    onError: (error: any) => {
      showMessage('error', error.message || config.errorMessage || 'Operation failed')
    },
    meta: {
      telemetry: {
        operation: config.operationName ?? 'mutation',
      },
    },
  })
}

export const createResourceMutation = <T extends Record<string, any>>(
  resourceType: string,
  operation: 'create' | 'update' | 'delete',
  request: (variables: T) => Promise<unknown>,
  nameField: keyof T,
  additionalKeys: string[] = []
) => {
  const baseMutation = createMutation<T>({
    request,
    invalidateKeys: [resourceType.toLowerCase() + 's', 'dropdown-data', ...additionalKeys],
    successMessage: (variables: T) => {
      const name = variables[nameField] as string
      const actions = { create: 'created', update: 'updated', delete: 'deleted' }
      return `${resourceType} "${name}" ${actions[operation]} successfully`
    },
    errorMessage: `Failed to ${operation} ${resourceType.toLowerCase()}`,
    operationName: `${resourceType}.${operation}`,
  })

  return () => {
    const mutation = baseMutation()
    const originalMutate = mutation.mutate

    mutation.mutate = (variables: T, options?: any) => {
      telemetryService.trackEvent('business.resource_operation', {
        'resource.type': resourceType.toLowerCase(),
        'resource.operation': operation,
        'resource.name': (variables[nameField] as string) || 'unknown',
        'resource.has_vault': Object.keys(variables).some(key => key.toLowerCase().includes('vault')),
        'resource.field_count': Object.keys(variables).length,
      })

      return originalMutate(variables, {
        ...options,
        onSuccess: (data: any, vars: T, context: any) => {
          telemetryService.trackEvent('business.resource_operation_success', {
            'resource.type': resourceType.toLowerCase(),
            'resource.operation': operation,
            'resource.name': (vars[nameField] as string) || 'unknown',
          })
          options?.onSuccess?.(data, vars, context)
        },
        onError: (error: any, vars: T, context: any) => {
          telemetryService.trackEvent('business.resource_operation_error', {
            'resource.type': resourceType.toLowerCase(),
            'resource.operation': operation,
            'resource.name': (vars[nameField] as string) || 'unknown',
            'resource.error': error.message || 'unknown_error',
          })
          options?.onError?.(error, vars, context)
        },
      })
    }

    return mutation
  }
}

export const createVaultUpdateMutation = <T extends Record<string, any>>(
  resourceType: string,
  request: (data: T) => Promise<unknown>,
  nameField: keyof T,
  vaultField: keyof T
) => createMutation<T>({
  request,
  invalidateKeys: [resourceType.toLowerCase() + 's'],
  successMessage: (variables) => `${resourceType} vault updated for "${variables[nameField]}"`,
  errorMessage: `Failed to update ${resourceType.toLowerCase()} vault`,
  transformData: (data) => ({
    ...data,
    [vaultField]: minifyJSON(data[vaultField] as string),
  }),
  operationName: `${resourceType}.updateVault`,
})
