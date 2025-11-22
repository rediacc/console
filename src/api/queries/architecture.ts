import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { extractTableData, parseDoubleEncodedJson, fixTripleEncodedFields } from '@/core/api/response'

interface GraphNode {
  nodeType: string
  nodeId: string
  name: string
  label: string
  hierarchyLevel: string
  [key: string]: any
}

interface GraphRelationship {
  source: string
  target: string
  relationshipType: string
  label: string
}

interface CompanyDataGraph {
  metadata: {
    currentUser: string
    userRole: string
    generatedAt: string
    dataFormat: string
  }
  nodes: {
    company: GraphNode[]
    users: GraphNode[]
    teams: GraphNode[]
    regions: GraphNode[]
    bridges: GraphNode[]
    machines: GraphNode[]
    repositories: GraphNode[]
    storages: GraphNode[]
  }
  relationships: {
    companyToTeams: GraphRelationship[]
    companyToRegions: GraphRelationship[]
    userToTeams: GraphRelationship[]
    regionToBridges: GraphRelationship[]
    teamToMachines: GraphRelationship[]
    bridgeToMachines: GraphRelationship[]
    teamToRepos: GraphRelationship[]
    teamToStorages: GraphRelationship[]
  }
  summary: {
    userTeamCount: number
    accessibleMachines: number
    totalQueueItems: number
    isAdministrator: boolean
    companyName: string
  }
}

export const useCompanyArchitecture = () => {
  return useQuery<CompanyDataGraph>({
    queryKey: ['companyArchitecture'],
    queryFn: async () => {
      const response = await apiClient.post('/GetCompanyDataGraphJson', {})
      
      // Check for failure
      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch company architecture')
      }
      
      // Extract the JSON string from the response
      const extractedData = extractTableData(response, 1, []) as any[]
      const jsonString = extractedData[0]?.companyDataGraph as string | undefined
      if (!jsonString) {
        throw new Error('No architecture data returned')
      }
      
      try {
        // Parse the double-encoded JSON structure
        const { metadata, nodes, relationships, summary } = parseDoubleEncodedJson<CompanyDataGraph>(
          jsonString, 
          ['metadata', 'nodes', 'relationships', 'summary']
        )
        
        // Fix triple-encoded fields
        fixTripleEncodedFields(nodes, ['users'])
        
        // Ensure all node arrays exist with defaults
        const nodeDefaults = ['machines', 'repositories', 'storages'] as const
        nodeDefaults.forEach(field => { 
          if (!nodes[field]) {
            (nodes as any)[field] = []
          }
        })
        
        return { metadata, nodes, relationships, summary }
      } catch {
        throw new Error('Invalid JSON data returned from server')
      }
    },
    staleTime: 60000, // Consider data fresh for 1 minute
    refetchInterval: 300000, // Refetch every 5 minutes
  })
}
