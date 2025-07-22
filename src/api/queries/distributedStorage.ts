import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { createResourceMutation, createVaultUpdateMutation, createMutation } from '@/api/utils/mutationFactory'

export interface DistributedStorageCluster {
  clusterName: string
  teamName: string
  status: string
  poolName: string
  poolPgNum: number
  poolSize: string
  osdDevice: string
  rbdImagePrefix: string
  healthCheckTimeout: number
  nodeCount: number
  vaultVersion: number
  vaultContent?: string
  created: string
  modified: string
}

export interface DistributedStorageNode {
  nodeName: string
  isPrimary: boolean
  added: string
}

// Get distributed storage clusters for a team or multiple teams
export const useDistributedStorageClusters = (teamFilter?: string | string[]) => {
  return useQuery<DistributedStorageCluster[]>({
    queryKey: ['distributedStorage', teamFilter],
    queryFn: async () => {
      if (!teamFilter || (Array.isArray(teamFilter) && teamFilter.length === 0)) return []
      
      // Build params based on teamFilter
      let params = {}
      
      if (Array.isArray(teamFilter)) {
        // Send comma-separated teams in a single request
        params = { teamName: teamFilter.join(',') }
      } else {
        // Single team
        params = { teamName: teamFilter }
      }
      
      const response = await apiClient.get('/ListDistributedStorageClusters', params)
      const data = response.resultSets?.[1]?.data || []
      const clusters = Array.isArray(data) ? data : []
      return clusters
        .filter((cluster: any) => cluster && cluster.clusterName)
        .map((cluster: any) => ({
          clusterName: cluster.clusterName,
          teamName: cluster.teamName,
          status: cluster.status || 'Unknown',
          poolName: cluster.poolName,
          poolPgNum: cluster.poolPgNum,
          poolSize: cluster.poolSize,
          osdDevice: cluster.osdDevice,
          rbdImagePrefix: cluster.rbdImagePrefix,
          healthCheckTimeout: cluster.healthCheckTimeout,
          nodeCount: cluster.nodeCount || 0,
          vaultVersion: cluster.vaultVersion || 1,
          vaultContent: cluster.vaultContent || '{}',
          created: cluster.created,
          modified: cluster.modified,
        }))
    },
    enabled: !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0),
    staleTime: 30 * 1000, // 30 seconds
  })
}

// Get single distributed storage cluster details including nodes
export const useDistributedStorageCluster = (teamName?: string, clusterName?: string) => {
  return useQuery<{ cluster: DistributedStorageCluster; nodes: DistributedStorageNode[] }>({
    queryKey: ['distributedStorage', teamName, clusterName],
    queryFn: async () => {
      if (!teamName || !clusterName) return { cluster: {} as DistributedStorageCluster, nodes: [] }
      
      const response = await apiClient.get('/GetDistributedStorageCluster', { teamName, clusterName })
      
      // Extract cluster data from first table
      const clusterData = response.resultSets?.[0]?.data?.[0]
      if (!clusterData) throw new Error('Cluster not found')
      
      const cluster: DistributedStorageCluster = {
        clusterName: clusterData.clusterName,
        teamName: clusterData.teamName,
        status: clusterData.status || 'Unknown',
        poolName: clusterData.poolName,
        poolPgNum: clusterData.poolPgNum,
        poolSize: clusterData.poolSize,
        osdDevice: clusterData.osdDevice,
        rbdImagePrefix: clusterData.rbdImagePrefix,
        healthCheckTimeout: clusterData.healthCheckTimeout,
        nodeCount: clusterData.nodeCount || 0,
        vaultVersion: clusterData.vaultVersion || 1,
        vaultContent: clusterData.vaultContent || '{}',
        created: clusterData.created,
        modified: clusterData.modified,
      }
      
      // Extract nodes from second table
      const nodesData = response.resultSets?.[1]?.data || []
      const nodes: DistributedStorageNode[] = nodesData.map((node: any) => ({
        nodeName: node.machineName,
        isPrimary: node.isPrimary || false,
        added: node.added,
      }))
      
      return { cluster, nodes }
    },
    enabled: !!teamName && !!clusterName,
    staleTime: 30 * 1000,
  })
}

// Create distributed storage cluster
export const useCreateDistributedStorageCluster = createMutation<{
  teamName: string
  clusterName: string
  poolName: string
  poolPgNum: number
  poolSize: string
  osdDevice: string
  rbdImagePrefix: string
  healthCheckTimeout: number
  clusterVault?: string
}>({
  endpoint: '/CreateDistributedStorageCluster',
  method: 'post',
  invalidateKeys: ['distributedStorage', 'teams'],
  successMessage: (vars) => `Distributed storage cluster "${vars.clusterName}" created successfully`,
  errorMessage: 'Failed to create distributed storage cluster',
  transformData: (data) => ({
    ...data,
    clusterVault: data.clusterVault || '{}'
  })
})

// Update distributed storage cluster vault
export const useUpdateDistributedStorageClusterVault = createVaultUpdateMutation<{
  teamName: string
  clusterName: string
  clusterVault: string
  vaultVersion: number
}>(
  'DistributedStorageCluster',
  '/UpdateDistributedStorageClusterVault',
  'clusterName',
  'clusterVault'
)

// Add machines to distributed storage
export const useAddMachinesToDistributedStorage = createMutation<{
  teamName: string
  clusterName: string
  machinesVault: string
}>({
  endpoint: '/AddMachinesToDistributedStorage',
  method: 'post',
  invalidateKeys: ['distributedStorage'],
  successMessage: 'Machines added to distributed storage cluster',
  errorMessage: 'Failed to add machines to distributed storage cluster'
})

// Remove machines from distributed storage
export const useRemoveMachinesFromDistributedStorage = createMutation<{
  teamName: string
  clusterName: string
  machinesVault: string
}>({
  endpoint: '/RemoveMachinesFromDistributedStorage',
  method: 'post',
  invalidateKeys: ['distributedStorage'],
  successMessage: 'Machines removed from distributed storage cluster',
  errorMessage: 'Failed to remove machines from distributed storage cluster'
})

// Update distributed storage cluster status
export const useUpdateDistributedStorageClusterStatus = createMutation<{
  teamName: string
  clusterName: string
  status: string
}>({
  endpoint: '/UpdateDistributedStorageClusterStatus',
  method: 'put',
  invalidateKeys: ['distributedStorage'],
  successMessage: (vars) => `Cluster status updated to "${vars.status}"`,
  errorMessage: 'Failed to update cluster status'
})

// Delete distributed storage cluster
export const useDeleteDistributedStorageCluster = createResourceMutation<{
  teamName: string
  clusterName: string
}>(
  'DistributedStorageCluster',
  'delete',
  '/DeleteDistributedStorageCluster',
  'clusterName',
  ['teams']
)