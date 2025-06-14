import { useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
import { minifyJSON } from '@/utils/json'

export interface MutationConfig<T> {
  endpoint: string
  method?: 'post' | 'put' | 'delete'
  invalidateKeys: string[] | ((variables: T) => string[])
  successMessage: (variables: T) => string
  errorMessage?: string
  transformData?: (data: T) => any
}

export const createMutation = <T>(config: MutationConfig<T>) => () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: T) => {
      const transformedData = config.transformData ? config.transformData(data) : data
      return await apiClient[config.method || 'post'](config.endpoint, transformedData)
    },
    onSuccess: (_, variables) => {
      const keys = typeof config.invalidateKeys === 'function' 
        ? config.invalidateKeys(variables) 
        : config.invalidateKeys
      keys.forEach(key => queryClient.invalidateQueries({ queryKey: [key] }))
      showMessage('success', config.successMessage(variables))
    },
    onError: (error: any) => {
      showMessage('error', error.message || config.errorMessage || 'Operation failed')
    },
  })
}

export const createResourceMutation = <T extends Record<string, any>>(
  resourceType: string,
  operation: 'create' | 'update' | 'delete',
  endpoint: string,
  nameField: keyof T,
  additionalKeys: string[] = []
) => createMutation<T>({
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