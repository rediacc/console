interface Repo {
  name: string
  size: number
  size_human: string
  modified: number
  modified_human: string
  mounted: boolean
  mount_path: string
  image_path: string
  accessible: boolean
  has_rediaccfile: boolean
  docker_running: boolean
  container_count: number
  has_services: boolean
  service_count: number
  total_volumes?: number
  internal_volumes?: number
  external_volumes?: number
  external_volume_names?: string[]
  volume_status?: 'safe' | 'warning' | 'none'
}

interface RepoCache {
  data: Repo[]
  timestamp: number
  taskId?: string
}

class RepoDataService {
  private cache: Map<string, RepoCache> = new Map()
  private readonly CACHE_DURATION = 5 * 60 * 1000 // 5 minutes cache
  
  /**
   * Get cached repo data for a machine
   */
  getCachedData(teamName: string, machineName: string): RepoCache | null {
    const key = `${teamName}:${machineName}`
    const cached = this.cache.get(key)
    
    if (!cached) return null
    
    // Check if cache is still valid
    const now = Date.now()
    if (now - cached.timestamp > this.CACHE_DURATION) {
      this.cache.delete(key)
      return null
    }
    
    return cached
  }
  
  /**
   * Store repo data in cache
   */
  setCachedData(teamName: string, machineName: string, data: Repo[], taskId?: string): void {
    const key = `${teamName}:${machineName}`
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      taskId
    })
  }
  
  /**
   * Invalidate cache for a specific machine
   */
  invalidateCache(teamName: string, machineName: string): void {
    const key = `${teamName}:${machineName}`
    this.cache.delete(key)
  }
  
  /**
   * Invalidate all caches
   */
  invalidateAllCaches(): void {
    this.cache.clear()
  }
  
  /**
   * Check if we have a pending task for this machine
   */
  getPendingTaskId(teamName: string, machineName: string): string | null {
    const key = `${teamName}:${machineName}`
    const cached = this.cache.get(key)
    return cached?.taskId || null
  }
  
  /**
   * Force refresh by invalidating and returning null
   */
  forceRefresh(teamName: string, machineName: string): null {
    this.invalidateCache(teamName, machineName)
    return null
  }
}

// Export singleton instance
export const repoDataService = new RepoDataService()