/**
 * Centralized Feature Flags Configuration
 *
 * This file manages all beta and development features in one place.
 * To hide a feature in production builds, set requiresLocalhost: true
 *
 * Usage:
 *   import { featureFlags } from '@/config/featureFlags'
 *   if (featureFlags.isEnabled('distributedStorage')) { ... }
 */

import { apiConnectionService } from '@/services/apiConnectionService'

export interface FeatureFlag {
  enabled: boolean
  requiresLocalhost?: boolean  // Only show when connected to localhost
  requiresBuildType?: 'DEBUG' | 'RELEASE'  // Only show in specific build type
  requiresExpertMode?: boolean  // Requires expert UI mode (checked separately in components)
  description?: string  // Description of the feature
}

class FeatureFlags {
  private isDevelopment = false

  constructor() {
    // Will be initialized after API connection is established
  }

  /**
   * Define all feature flags here
   * This is the single source of truth for all beta features
   */
  private flags: Record<string, FeatureFlag> = {
    // Distributed Storage - Beta feature
    distributedStorage: {
      enabled: false,
      requiresLocalhost: true,  // Hide in production builds
      requiresExpertMode: true,
      description: 'Distributed storage cluster management - allows creating and managing storage clusters'
    },

    // Marketplace - Beta feature
    marketplace: {
      enabled: false,
      requiresLocalhost: true,  // Hide in production builds
      description: 'Template marketplace for quick deployments'
    },

    // Assign to Cluster - Beta feature (menu item in MachineTable)
    assignToCluster: {
      enabled: false,
      requiresLocalhost: true,  // Hide in production builds
      requiresExpertMode: true,
      description: 'Assign machines to distributed storage clusters'
    },

    // Architecture - Beta feature
    architecture: {
      enabled: false,
      requiresLocalhost: true,  // Hide in production builds
      requiresExpertMode: true,
      description: 'System architecture visualization and dependency management'
    },

    // Login Advanced Options - Beta feature (encryption password on login page)
    loginAdvancedOptions: {
      enabled: false,
      requiresLocalhost: true,  // Hide in production builds
      description: 'Advanced login options including master password / encryption password field'
    },

    // Plugins - Beta feature (vault-based plugin containers)
    plugins: {
      enabled: false,
      requiresLocalhost: true,  // Hide in production builds
      description: 'Plugin containers system - vault-based feature for custom service containers'
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

    // Feature doesn't exist or is explicitly disabled
    if (!flag || !flag.enabled) {
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
}

// Export singleton instance
export const featureFlags = new FeatureFlags()
