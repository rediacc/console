/**
 * ============================================================================
 * CENTRALIZED FEATURE FLAGS CONFIGURATION
 * ============================================================================
 *
 * This file manages all beta and development features in one place.
 * Features are controlled by requirement flags that determine visibility.
 *
 * ============================================================================
 * BEHAVIOR MATRIX
 * ============================================================================
 *
 * | Feature Type            | Production | Production + Ctrl+Shift+E | Localhost | Localhost + Ctrl+Shift+E |
 * |-------------------------|-----------|---------------------------|-----------|-------------------------|
 * | requiresLocalhost       | Hidden    | Hidden                    | Visible   | Visible                 |
 * | requiresPowerMode       | Hidden    | Visible                   | Hidden    | Visible                 |
 * | requiresExpertMode      | Hidden    | Hidden                    | Hidden*   | Visible                 |
 * | enabled: true (default) | Visible   | Visible                   | Visible   | Visible                 |
 * | enabled: false          | Hidden    | Hidden                    | Hidden    | Visible                 |
 *
 * * requiresExpertMode also requires expert mode toggle in UI (separate from this system)
 *
 * NOTE: "Localhost" column refers to being connected to localhost API endpoint.
 *       "Localhost + Ctrl+Shift+E" means running on localhost domain (window.location.hostname).
 *       These are different conditions:
 *         - Localhost API: Checked via apiConnectionService (isDevelopment flag)
 *         - Localhost Domain: Checked via window.location.hostname
 *       Edge case: On localhost:5173 connected to production API, requiresLocalhost features
 *       will be hidden until you press Ctrl+Shift+E (which checks domain, not API).
 *
 * ============================================================================
 * KEYBOARD SHORTCUT: Ctrl+Shift+E
 * ============================================================================
 *
 * On Production domains:
 *   - Toggles "Power Mode"
 *   - Shows features with requiresPowerMode: true (e.g., API endpoint selector)
 *   - Does NOT show features with requiresLocalhost: true
 *
 * On Localhost domain:
 *   - Toggles "Localhost Mode"
 *   - Shows ALL features (ignores all requirement flags, even enabled: false)
 *   - Blue banner appears: "Localhost Mode: All features enabled"
 *
 * ============================================================================
 * FEATURE FLAG PROPERTIES
 * ============================================================================
 *
 * enabled?: boolean
 *   - Optional, defaults to true if not specified
 *   - Only use enabled: false for truly broken/deprecated features
 *   - If a feature has requirement flags, DO NOT specify enabled
 *
 * requiresLocalhost?: boolean
 *   - Feature only visible when connected to localhost API
 *   - Use for beta/development features not ready for production
 *   - Example: marketplace, distributedStorage, queue
 *
 * requiresPowerMode?: boolean
 *   - Feature revealed by Ctrl+Shift+E on production domains
 *   - Use for advanced admin tools that should be accessible in production
 *   - Example: apiEndpointSelector, versionSelector
 *
 * requiresExpertMode?: boolean
 *   - Feature requires expert mode toggle in UI (separate system)
 *   - Usually combined with requiresLocalhost
 *   - Checked separately in components, not by this service
 *
 * requiresBuildType?: 'DEBUG' | 'RELEASE'
 *   - Feature only shows in specific build type
 *   - Rarely used
 *
 * ============================================================================
 * USAGE EXAMPLES
 * ============================================================================
 *
 * // Check if feature is enabled
 * import { featureFlags } from '@/config/featureFlags'
 * if (featureFlags.isEnabled('distributedStorage')) {
 *   // Show feature
 * }
 *
 * // Beta feature (localhost-only)
 * marketplace: {
 *   requiresLocalhost: true,
 *   description: 'Template marketplace'
 * }
 *
 * // Power mode feature (accessible in production with Ctrl+Shift+E)
 * apiEndpointSelector: {
 *   requiresPowerMode: true,
 *   description: 'API endpoint selector'
 * }
 *
 * // Production feature (always visible)
 * dashboard: {
 *   description: 'Main dashboard'
 * }
 *
 * // Truly disabled feature
 * deprecatedFeature: {
 *   enabled: false,
 *   description: 'Old feature removed in v2.0'
 * }
 *
 * ============================================================================
 * BEST PRACTICES
 * ============================================================================
 *
 * 1. New beta features → Use requiresLocalhost: true (no enabled flag needed)
 * 2. Admin power tools → Use requiresPowerMode: true
 * 3. Production features → Just add description, no flags needed
 * 4. To release a feature → Remove requiresLocalhost flag
 * 5. Broken features → Set enabled: false temporarily
 * 6. Deprecated features → Set enabled: false permanently (or remove from file)
 *
 * ============================================================================
 */

import { apiConnectionService } from '@/services/apiConnectionService'

export interface FeatureFlag {
  enabled?: boolean  // If not specified, defaults to true. Only use false for truly disabled/deprecated features
  requiresLocalhost?: boolean  // Only show when connected to localhost
  requiresBuildType?: 'DEBUG' | 'RELEASE'  // Only show in specific build type
  requiresExpertMode?: boolean  // Requires expert UI mode (checked separately in components)
  requiresPowerMode?: boolean  // Can be revealed via keyboard shortcuts (session-only)
  description?: string  // Description of the feature
}

class FeatureFlags {
  private isDevelopment = false
  private isPowerModeActive: boolean = false  // Global power mode state (session-only)
  private isLocalhostModeActive: boolean = false  // Localhost mode state (session-only)

  constructor() {
    // Will be initialized after API connection is established
  }

  /**
   * Check if running on localhost domain
   * @returns true if hostname is localhost or 127.0.0.1
   */
  private isRunningOnLocalhost(): boolean {
    if (typeof window === 'undefined') return false
    const hostname = window.location.hostname
    return hostname === 'localhost' || hostname === '127.0.0.1'
  }

  /**
   * Define all feature flags here
   * This is the single source of truth for all beta features
   */
  private flags: Record<string, FeatureFlag> = {
    // Distributed Storage - Beta feature
    distributedStorage: {
      requiresLocalhost: true,  // Hide in production builds
      requiresExpertMode: true,
      description: 'Distributed storage cluster management - allows creating and managing storage clusters'
    },

    // Marketplace - Beta feature
    marketplace: {
      requiresLocalhost: true,  // Hide in production builds
      description: 'Template marketplace for quick deployments'
    },

    // Assign to Cluster - Beta feature (menu item in MachineTable)
    assignToCluster: {
      requiresLocalhost: true,  // Hide in production builds
      requiresExpertMode: true,
      description: 'Assign machines to distributed storage clusters'
    },

    // Architecture - Beta feature
    architecture: {
      requiresLocalhost: true,  // Hide in production builds
      requiresExpertMode: true,
      description: 'System architecture visualization and dependency management'
    },

    // Login Advanced Options - Beta feature (encryption password on login page)
    loginAdvancedOptions: {
      requiresLocalhost: true,  // Hide in production builds
      description: 'Advanced login options including master password / encryption password field'
    },

    // Plugins - Beta feature (vault-based plugin containers)
    plugins: {
      requiresLocalhost: true,  // Hide in production builds
      description: 'Plugin containers system - vault-based feature for custom service containers'
    },

    // API Endpoint Selector - Power mode feature
    apiEndpointSelector: {
      requiresPowerMode: true,
      description: 'API endpoint selector dropdown for switching between API backends'
    },

    // Version Selector - Power mode feature
    versionSelector: {
      requiresPowerMode: true,
      description: 'Version selector dropdown for switching between deployed versions'
    },

    // Queue Management - Expert mode feature
    queueManagement: {
      requiresLocalhost: true,
      requiresExpertMode: true,
      description: 'Queue page for viewing and managing task queues'
    },

    // Audit Logs - Expert mode feature
    auditLogs: {
      requiresLocalhost: true,
      requiresExpertMode: true,
      description: 'Audit logs page for viewing system activity and changes'
    },

    // Vault Version Columns - Expert mode feature
    vaultVersionColumns: {
      requiresLocalhost: true,
      requiresExpertMode: true,
      description: 'Show vault version columns in resource tables for debugging purposes'
    },

    // Advanced Vault Editor - Expert mode feature
    advancedVaultEditor: {
      requiresLocalhost: true,
      requiresExpertMode: true,
      description: 'Raw JSON editor panel in vault editor - advanced/dangerous feature'
    },

    // Regions & Infrastructure - Expert mode feature
    regionsInfrastructure: {
      requiresLocalhost: true,
      requiresExpertMode: true,
      description: 'Regions and infrastructure management section in System page'
    },

    // Danger Zone - Expert mode feature
    dangerZone: {
      requiresLocalhost: true,
      requiresExpertMode: true,
      description: 'Danger Zone section including block users, export/import data, and encryption settings'
    },

    // Disable Bridge - Always hidden for all users
    disableBridge: {
      enabled: true,
      description: 'Hide all bridge-related UI components including bridge tables, forms, and fields'
    },

    // Hide Danger Zone - DEPRECATED: Use dangerZone flag instead (kept for backwards compatibility)
    hideDangerZone: {
      enabled: true,
      description: '[DEPRECATED] Use dangerZone flag instead. Hide the Danger Zone section including block users, export/import data, and encryption settings'
    },

    // Example: Future feature that's disabled for everyone
    // newFeatureX: {
    //   enabled: false,
    //   description: 'Upcoming feature X - not ready yet'
    // },

    // Example: Feature only for DEBUG builds
    // debugTooling: {
    //   enabled: true,
    //   requiresBuildType: 'DEBUG',
    //   description: 'Advanced debugging tools'
    // },
  }

  /**
   * Check if a feature is enabled
   * @param featureName - The name of the feature to check
   * @returns true if the feature should be visible/enabled
   */
  isEnabled(featureName: string): boolean {
    const flag = this.flags[featureName]

    // Feature doesn't exist
    if (!flag) {
      return false
    }

    // Localhost mode: Enable ALL features when active (ignore enabled flag)
    if (this.isRunningOnLocalhost() && this.isLocalhostModeActive) {
      return true
    }

    // Feature is explicitly disabled (enabled: false)
    // If enabled is not specified, it defaults to true
    if (flag.enabled === false) {
      return false
    }

    // Check power mode requirement
    if (flag.requiresPowerMode && !this.isPowerModeActive) {
      return false
    }

    // Check localhost requirement
    if (flag.requiresLocalhost && !this.isDevelopment) {
      return false
    }

    // Check build type requirement
    if (flag.requiresBuildType) {
      const currentBuildType = import.meta.env.VITE_BUILD_TYPE || 'DEBUG'
      if (currentBuildType !== flag.requiresBuildType) {
        return false
      }
    }

    return true
  }

  /**
   * Get all enabled features
   * @returns Array of enabled feature names
   */
  getEnabledFeatures(): string[] {
    return Object.keys(this.flags).filter(name => this.isEnabled(name))
  }

  /**
   * Get feature flag details
   * @param featureName - The name of the feature
   * @returns The feature flag configuration or undefined
   */
  getFeature(featureName: string): FeatureFlag | undefined {
    return this.flags[featureName]
  }

  /**
   * Update development state based on current API connection
   * This should be called after API connection is established
   */
  updateDevelopmentState(): void {
    const endpointInfo = apiConnectionService.getEndpointInfo()
    this.isDevelopment = endpointInfo?.type === 'localhost'

    if (import.meta.env.DEV) {
      console.log('[FeatureFlags] Development state updated:', {
        isDevelopment: this.isDevelopment,
        endpointType: endpointInfo?.type,
        buildType: import.meta.env.VITE_BUILD_TYPE,
        enabledFeatures: this.getEnabledFeatures()
      })
    }
  }

  /**
   * Get development state
   * @returns true if connected to localhost
   */
  isDevelopmentMode(): boolean {
    return this.isDevelopment
  }

  /**
   * Get current build type
   * @returns 'DEBUG' or 'RELEASE'
   */
  getBuildType(): 'DEBUG' | 'RELEASE' {
    const buildType = import.meta.env.VITE_BUILD_TYPE || 'DEBUG'
    return buildType === 'RELEASE' ? 'RELEASE' : 'DEBUG'
  }

  /**
   * Toggle global power mode (session-only, not persisted)
   * On localhost domain, this toggles localhost mode (enables ALL features)
   * On non-localhost domains, this toggles power mode (enables only power mode features)
   * @returns The new mode state after toggle
   */
  togglePowerMode(): boolean {
    const onLocalhost = this.isRunningOnLocalhost()

    if (onLocalhost) {
      // Toggle localhost mode
      this.isLocalhostModeActive = !this.isLocalhostModeActive

      if (import.meta.env.DEV) {
        console.log(`[LocalhostMode] Localhost mode ${this.isLocalhostModeActive ? 'enabled' : 'disabled'}`)
      }

      return this.isLocalhostModeActive
    } else {
      // Toggle power mode (original behavior)
      this.isPowerModeActive = !this.isPowerModeActive

      if (import.meta.env.DEV) {
        console.log(`[PowerMode] Global power mode ${this.isPowerModeActive ? 'enabled' : 'disabled'}`)
      }

      return this.isPowerModeActive
    }
  }

  /**
   * Enable global power mode (session-only, not persisted)
   */
  enablePowerMode(): void {
    this.isPowerModeActive = true

    if (import.meta.env.DEV) {
      console.log('[PowerMode] Global power mode enabled')
    }
  }

  /**
   * Check if global power mode is enabled
   * @returns true if power mode is active
   */
  isPowerModeEnabled(): boolean {
    return this.isPowerModeActive
  }

  /**
   * Check if localhost mode is enabled
   * @returns true if localhost mode is active
   */
  isLocalhostModeEnabled(): boolean {
    return this.isLocalhostModeActive
  }
}

// Export singleton instance
export const featureFlags = new FeatureFlags()
