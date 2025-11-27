/**
 * Version Service
 *
 * Fetches and manages application version information from version.json.
 * This file is created during deployment and contains the actual version tag.
 */

interface VersionInfo {
  version: string
  buildDate?: string
  gitCommit?: string
  gitCommitShort?: string
}

class VersionService {
  private versionCache: VersionInfo | null = null
  private fetchPromise: Promise<VersionInfo> | null = null

  /**
   * Fetches the version information from version.json
   * Returns cached result if available
   */
  async getVersion(): Promise<VersionInfo> {
    // Return cached version if available
    if (this.versionCache) {
      return this.versionCache
    }

    // Return existing fetch promise if already fetching
    if (this.fetchPromise) {
      return this.fetchPromise
    }

    // Create new fetch promise
    this.fetchPromise = this.fetchVersionFromFile()

    try {
      this.versionCache = await this.fetchPromise
      return this.versionCache
    } finally {
      this.fetchPromise = null
    }
  }

  /**
   * Fetches version.json file from the server
   */
  private async fetchVersionFromFile(): Promise<VersionInfo> {
    try {
      // Fetch version.json relative to the current base path
      // This works for both root (/) and versioned (/versions/vX.Y.Z/) deployments
      const response = await fetch('./version.json')

      if (!response.ok) {
        throw new Error(`Failed to fetch version.json: ${response.status}`)
      }

      const data = await response.json() as VersionInfo

      // Validate the response has a version field
      if (!data.version) {
        throw new Error('version.json missing version field')
      }

      return data
    } catch (error) {
      console.warn('Failed to fetch version from version.json, using fallback', error)

      // Fallback to build-time version from Vite
      return {
        version: import.meta.env.VITE_APP_VERSION || 'unknown',
      }
    }
  }

  /**
   * Formats the version for display
   * Ensures version has 'v' prefix
   */
  formatVersion(version: string): string {
    if (version === 'dev' || version === 'development' || version === 'unknown') {
      return 'Development'
    }

    // If it looks like a commit hash (40 chars, all hex), shorten it
    if (version.length === 40 && /^[0-9a-f]+$/i.test(version)) {
      return `v${version.substring(0, 7)}`
    }

    // Ensure 'v' prefix
    return version.startsWith('v') ? version : `v${version}`
  }

  /**
   * Clears the cached version (useful for testing)
   */
  clearCache(): void {
    this.versionCache = null
    this.fetchPromise = null
  }
}

export const versionService = new VersionService()
