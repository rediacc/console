import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

export interface DashboardMetrics {
  totalTeams: number
  totalMachines: number
  totalRepositories: number
  totalUsers: number
  activeQueueItems: number
  completedQueueItems: number
  failedQueueItems: number
  resourceUsageByTeam: Array<{
    teamName: string
    machines: number
    repositories: number
    storage: number
    queueItems: number
  }>
  queueActivityByDay: Array<{
    date: string
    created: number
    completed: number
    failed: number
  }>
  systemHealth: {
    activeBridges: number
    totalBridges: number
    activeRegions: number
    totalRegions: number
  }
}

export interface QueueAnalytics {
  statusDistribution: Array<{
    status: string
    count: number
  }>
  processingTimeStats: {
    average: number
    min: number
    max: number
  }
  queueItemsByMachine: Array<{
    machineName: string
    count: number
  }>
  queueTrend: Array<{
    date: string
    count: number
  }>
}

export interface TeamComparison {
  teams: Array<{
    teamName: string
    resources: {
      machines: number
      repositories: number
      storage: number
      schedules: number
    }
    activity: {
      queueItems: number
      lastActive: string
    }
  }>
}

export interface ResourceUsageTrends {
  trends: Array<{
    month: string
    teams: number
    machines: number
    repositories: number
    storage: number
    queueItems: number
  }>
}

// Get dashboard metrics
export const useDashboardMetrics = (daysBack: number = 30) => {
  return useQuery({
    queryKey: ['dashboard-metrics', daysBack],
    queryFn: async () => {
      // Since the GetDashboardMetrics endpoint might not exist yet,
      // we'll aggregate data from existing endpoints
      
      // Get teams
      const teamsResponse = await apiClient.get('/GetCompanyTeams')
      const teams = teamsResponse.tables[1]?.data || []
      
      // Get regions
      const regionsResponse = await apiClient.get('/GetCompanyRegions')
      const regions = regionsResponse.tables[1]?.data || []
      
      // Get users
      const usersResponse = await apiClient.get('/GetCompanyUsers')
      const users = usersResponse.tables[1]?.data || []
      
      // Calculate totals
      const totalTeams = teams.length
      const totalMachines = teams.reduce((sum: number, team: any) => sum + (team.machineCount || 0), 0)
      const totalRepositories = teams.reduce((sum: number, team: any) => sum + (team.repoCount || 0), 0)
      const totalUsers = users.length
      
      // Calculate resource usage by team
      const resourceUsageByTeam = teams.map((team: any) => ({
        teamName: team.teamName,
        machines: team.machineCount || 0,
        repositories: team.repoCount || 0,
        storage: team.storageCount || 0,
        queueItems: 0 // Would need queue data
      }))
      
      // System health
      const systemHealth = {
        activeBridges: regions.reduce((sum: number, region: any) => sum + (region.bridgeCount || 0), 0),
        totalBridges: regions.reduce((sum: number, region: any) => sum + (region.bridgeCount || 0), 0),
        activeRegions: regions.length,
        totalRegions: regions.length
      }
      
      // Mock some data for demonstration
      const mockMetrics: DashboardMetrics = {
        totalTeams,
        totalMachines,
        totalRepositories,
        totalUsers,
        activeQueueItems: 23,
        completedQueueItems: 156,
        failedQueueItems: 3,
        resourceUsageByTeam,
        queueActivityByDay: generateMockQueueActivity(daysBack),
        systemHealth
      }
      
      return mockMetrics
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
}

// Get queue analytics
export const useQueueAnalytics = (teamName?: string, daysBack: number = 7) => {
  return useQuery({
    queryKey: ['queue-analytics', teamName, daysBack],
    queryFn: async () => {
      // Mock data for demonstration
      const mockAnalytics: QueueAnalytics = {
        statusDistribution: [
          { status: 'pending', count: 15 },
          { status: 'processing', count: 8 },
          { status: 'completed', count: 156 },
          { status: 'failed', count: 3 }
        ],
        processingTimeStats: {
          average: 45.3,
          min: 12,
          max: 234
        },
        queueItemsByMachine: [
          { machineName: 'prod-server-1', count: 45 },
          { machineName: 'prod-server-2', count: 38 },
          { machineName: 'dev-server-1', count: 27 },
          { machineName: 'staging-server-1', count: 22 }
        ],
        queueTrend: generateMockQueueTrend(daysBack)
      }
      
      return mockAnalytics
    },
    staleTime: 5 * 60 * 1000,
  })
}

// Get team comparison metrics
export const useTeamComparison = () => {
  return useQuery({
    queryKey: ['team-comparison'],
    queryFn: async () => {
      const teamsResponse = await apiClient.get('/GetCompanyTeams')
      const teams = teamsResponse.tables[1]?.data || []
      
      const comparison: TeamComparison = {
        teams: teams.map((team: any) => ({
          teamName: team.teamName,
          resources: {
            machines: team.machineCount || 0,
            repositories: team.repoCount || 0,
            storage: team.storageCount || 0,
            schedules: team.scheduleCount || 0
          },
          activity: {
            queueItems: Math.floor(Math.random() * 50), // Mock data
            lastActive: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString()
          }
        }))
      }
      
      return comparison
    },
    staleTime: 10 * 60 * 1000, // 10 minutes
  })
}

// Helper functions to generate mock data
function generateMockQueueActivity(days: number) {
  const activity = []
  const now = new Date()
  
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    
    activity.push({
      date: date.toISOString().split('T')[0],
      created: Math.floor(Math.random() * 20) + 5,
      completed: Math.floor(Math.random() * 18) + 3,
      failed: Math.floor(Math.random() * 3)
    })
  }
  
  return activity
}

function generateMockQueueTrend(days: number) {
  const trend = []
  const now = new Date()
  
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    
    trend.push({
      date: date.toISOString().split('T')[0],
      count: Math.floor(Math.random() * 30) + 10
    })
  }
  
  return trend
}