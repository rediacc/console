/**
 * API Connection Service
 * Manages API endpoint selection with fallback mechanism
 * Performs health checks and caches the working endpoint for the session
 */

import axios from 'axios'

export type BuildType = 'DEBUG' | 'RELEASE'
export type EndpointType = 'localhost' | 'sandbox' | 'production'

interface EndpointConfig {
  url: string
  type: EndpointType
  isAvailable: boolean
}

class ApiConnectionService {
  private selectedEndpoint: EndpointConfig | null = null
  private buildType: BuildType = 'DEBUG'
  private healthCheckPerformed = false

  constructor() {
    // Determine build type from environment
    const envBuildType = import.meta.env.VITE_BUILD_TYPE || import.meta.env.MODE
    this.buildType = envBuildType === 'production' || envBuildType === 'RELEASE' ? 'RELEASE' : 'DEBUG'
  }

  /**
   * Get localhost API URL
   */
  private getLocalhostUrl(): string {
    const port = import.meta.env.VITE_HTTP_PORT || '7322'
    return `http://localhost:${port}/api`
  }

  /**
   * Get sandbox API URL
   */
  private getSandboxUrl(): string {
    return import.meta.env.VITE_SANDBOX_API_URL || 'https://sandbox.rediacc.com/api'
  }

  /**
   * Perform health check on an endpoint
   */
  private async checkEndpointHealth(url: string): Promise<boolean> {
    try {
      // Try a simple GET request to the API endpoint
      // Using a lightweight endpoint that doesn't require authentication
      const response = await axios.get(`${url}/StoredProcedure/GetSystemStatus`, {
        timeout: 3000, // 3 second timeout for health check
        validateStatus: (status) => status < 500 // Accept any non-5xx status
      })
      return true
    } catch (error) {
      console.warn(`Health check failed for ${url}:`, error)
      return false
    }
  }

  /**
   * Perform initial connection test and select appropriate endpoint
   * This is called once at application startup
   */
  async performStartupHealthCheck(): Promise<EndpointConfig> {
    // Return cached result if already performed
    if (this.healthCheckPerformed && this.selectedEndpoint) {
      return this.selectedEndpoint
    }

    console.log(`[API Connection] Build type: ${this.buildType}`)

    // RELEASE builds: Use relative /api path for production (same domain)
    // This ensures production deployments ONLY use their own backend
    if (this.buildType === 'RELEASE') {
      this.selectedEndpoint = {
        url: '/api',  // Relative path - serves from same domain
        type: 'production',
        isAvailable: true
      }
      this.healthCheckPerformed = true
      console.log('[API Connection] Using production endpoint (same domain /api)')
      return this.selectedEndpoint
    }

    // DEBUG builds: For development and open-source contributors
    // Try localhost first, then fallback to sandbox if needed
    const localhostUrl = this.getLocalhostUrl()
    const sandboxUrl = this.getSandboxUrl()

    console.log('[API Connection] DEBUG mode: Checking localhost availability...')
    const localhostAvailable = await this.checkEndpointHealth(localhostUrl)

    if (localhostAvailable) {
      this.selectedEndpoint = {
        url: localhostUrl,
        type: 'localhost',
        isAvailable: true
      }
      console.log('[API Connection] ✓ Using localhost endpoint')
    } else {
      // Sandbox fallback ONLY in DEBUG mode for open-source developers
      console.warn('[API Connection] ⚠️  NOTICE: Localhost unavailable, using sandbox environment')
      console.warn('[API Connection] ⚠️  This is only suitable for development/testing, not production')
      this.selectedEndpoint = {
        url: sandboxUrl,
        type: 'sandbox',
        isAvailable: true
      }
      console.log('[API Connection] ✓ Using sandbox endpoint (DEBUG mode fallback)')
    }

    this.healthCheckPerformed = true
    return this.selectedEndpoint
  }

  /**
   * Get the currently selected endpoint
   */
  getSelectedEndpoint(): EndpointConfig | null {
    return this.selectedEndpoint
  }

  /**
   * Get the API URL to use
   */
  async getApiUrl(): Promise<string> {
    if (!this.selectedEndpoint) {
      await this.performStartupHealthCheck()
    }
    return this.selectedEndpoint!.url
  }

  /**
   * Get endpoint display information
   */
  getEndpointInfo(): { url: string; type: string; label: string; warning?: boolean } | null {
    if (!this.selectedEndpoint) {
      return null
    }

    const { url, type } = this.selectedEndpoint
    let label = ''
    let warning = false
    
    if (type === 'localhost') {
      label = 'Local Development'
    } else if (type === 'sandbox') {
      label = 'Sandbox Environment (DEBUG)'
      warning = true // Show warning when using sandbox
    } else if (type === 'production') {
      label = 'Production'
    }

    return {
      url,
      type,
      label,
      warning
    }
  }

  /**
   * Reset the service (useful for testing)
   */
  reset(): void {
    this.selectedEndpoint = null
    this.healthCheckPerformed = false
  }

  /**
   * Get build type
   */
  getBuildType(): BuildType {
    return this.buildType
  }
}

// Export singleton instance
export const apiConnectionService = new ApiConnectionService()