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

interface VersionsManifest {
  latest: string
  versions: string[]
}

class VersionService {
  private versionCache: VersionInfo | null = null
  private fetchPromise: Promise<VersionInfo> | null = null
  private versionsCache: VersionsManifest | null = null
  private versionsFetchPromise: Promise<VersionsManifest> | null = null

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
   * Fetches all available versions from versions.json manifest
   * Returns cached result if available
   */
  async getAllVersions(): Promise<VersionsManifest> {
    // Return cached versions if available
    if (this.versionsCache) {
      return this.versionsCache
    }

    // Return existing fetch promise if already fetching
    if (this.versionsFetchPromise) {
      return this.versionsFetchPromise
    }

    // Create new fetch promise
    this.versionsFetchPromise = this.fetchVersionsManifest()

    try {
      this.versionsCache = await this.versionsFetchPromise
      return this.versionsCache
    } finally {
      this.versionsFetchPromise = null
    }
  }

  /**
   * Fetches versions.json manifest from the root
   */
  private async fetchVersionsManifest(): Promise<VersionsManifest> {
    try {
      // Always fetch from root /versions.json
      const response = await fetch('/versions.json')

      if (!response.ok) {
        throw new Error(`Failed to fetch versions.json: ${response.status}`)
      }

      const data = await response.json() as VersionsManifest

      // Validate the response
      if (!data.latest || !Array.isArray(data.versions)) {
        throw new Error('versions.json has invalid structure')
      }

      return data
    } catch (error) {
      console.warn('Failed to fetch versions.json, using fallback', error)

      // Fallback to current version only
      const currentVersionInfo = await this.getVersion()
      return {
        latest: currentVersionInfo.version,
        versions: [currentVersionInfo.version]
      }
    }
  }

  /**
   * Detects if the app is running in local development
   */
  isLocalDevelopment(): boolean {
    return window.location.hostname === 'localhost' ||
           window.location.hostname === '127.0.0.1'
  }

  /**
   * Gets the current version from the URL if on a versioned deployment
   * Returns null if on root deployment
   */
  getCurrentVersion(): string | null {
    const pathname = window.location.pathname
    const versionMatch = pathname.match(/^\/versions\/(v\d+\.\d+\.\d+)/)
    return versionMatch ? versionMatch[1] : null
  }

  /**
   * Clears the cached version (useful for testing)
   */
  clearCache(): void {
    this.versionCache = null
    this.fetchPromise = null
    this.versionsCache = null
    this.versionsFetchPromise = null
  }
}

export const versionService = new VersionService()
