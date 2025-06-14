import { createResourceQuery, dataExtractors, filters, createFieldMapper } from '@/api/utils/queryFactory'
import { createResourceMutation, createVaultUpdateMutation, createMutation } from '@/api/utils/mutationFactory'
import type { Machine } from '@/types'

// Get machines for a team, multiple teams, or all machines
export const useMachines = createResourceQuery<Machine>({
  endpoint: '/GetTeamMachines',
  queryKey: 'machines',
  dataExtractor: dataExtractors.primaryOrSecondary,
  filter: filters.hasName('machineName'),
  mapper: createFieldMapper<Machine>({
    machineName: 'machineName',
    teamName: 'teamName',
    bridgeName: 'bridgeName',
    regionName: 'regionName',
    queueCount: 'queueCount',
    vaultVersion: 'vaultVersion',
    vaultContent: 'vaultContent'
  })
})

// Create machine
export const useCreateMachine = createMutation<{
  teamName: string
  bridgeName: string
  machineName: string
  machineVault?: string
}>({
  endpoint: '/CreateMachine',
  method: 'post',
  invalidateKeys: ['machines', 'teams', 'bridges', 'dropdown-data'],
  successMessage: (vars) => `Machine "${vars.machineName}" created successfully`,
  errorMessage: 'Failed to create machine',
  transformData: (data) => ({
    ...data,
    machineVault: data.machineVault || '{}'
  })
})

// Update machine name
export const useUpdateMachineName = createMutation<{
  teamName: string
  currentMachineName: string
  newMachineName: string
}>({
  endpoint: '/UpdateMachineName',
  method: 'put',
  invalidateKeys: ['machines', 'dropdown-data'],
  successMessage: (vars) => `Machine renamed to "${vars.newMachineName}"`,
  errorMessage: 'Failed to update machine name'
})

// Update machine bridge assignment
export const useUpdateMachineBridge = createMutation<{
  teamName: string
  machineName: string
  newBridgeName: string
}>({
  endpoint: '/UpdateMachineAssignedBridge',
  method: 'put',
  invalidateKeys: ['machines', 'bridges'],
  successMessage: (vars) => `Machine "${vars.machineName}" reassigned to bridge "${vars.newBridgeName}"`,
  errorMessage: 'Failed to update machine bridge'
})

// Update machine vault
export const useUpdateMachineVault = createVaultUpdateMutation<{
  teamName: string
  machineName: string
  machineVault: string
  vaultVersion: number
}>(
  'Machine',
  '/UpdateMachineVault',
  'machineName',
  'machineVault'
)

// Delete machine
export const useDeleteMachine = createResourceMutation<{
  teamName: string
  machineName: string
}>(
  'Machine',
  'delete',
  '/DeleteMachine',
  'machineName',
  ['teams', 'bridges']
)