import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

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
    schedules: GraphNode[]
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
    teamToSchedules: GraphRelationship[]
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
      
      // The response is already parsed by apiClient, which returns response.data
      const data = response
      
      // Check for failure
      if (data.failure !== 0) {
        throw new Error(data.errors?.join(', ') || 'Failed to fetch company architecture')
      }
      
      // Get the JSON string from the second table (index 1), lowercase field name
      const jsonString = data.tables?.[1]?.data?.[0]?.companyDataGraph
      if (!jsonString) {
        throw new Error('No architecture data returned')
      }
      
      try {
        // Parse the double-encoded JSON
        const parsedData = JSON.parse(jsonString)
        
        // Parse each section which is also JSON-encoded
        const metadata = JSON.parse(parsedData.metadata)
        const nodes = JSON.parse(parsedData.nodes)
        const relationships = JSON.parse(parsedData.relationships)
        const summary = JSON.parse(parsedData.summary)
        
        // Fix the users field if it's a string (appears to be triple-encoded)
        if (typeof nodes.users === 'string') {
          nodes.users = JSON.parse(nodes.users)
        }
        
        // Ensure all node arrays exist
        nodes.machines = nodes.machines || []
        nodes.repositories = nodes.repositories || []
        nodes.schedules = nodes.schedules || []
        nodes.storages = nodes.storages || []
        
        return {
          metadata,
          nodes,
          relationships,
          summary
        }
      } catch (e) {
        throw new Error('Invalid JSON data returned from server')
      }
    },
    staleTime: 60000, // Consider data fresh for 1 minute
    refetchInterval: 300000, // Refetch every 5 minutes
  })
}