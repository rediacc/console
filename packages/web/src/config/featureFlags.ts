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
 * | Feature Type            | Production | Production + Ctrl+Shift+E | Localhost Domain | Localhost + Ctrl+Shift+E |
 * |-------------------------|-----------|---------------------------|------------------|-------------------------|
 * | requiresLocalhost       | Hidden    | Hidden                    | Hidden           | Visible                 |
 * | requiresPowerMode       | Hidden    | Visible                   | Hidden           | Visible                 |
 * | requiresExpertMode      | Hidden    | Hidden                    | Hidden           | Visible                 |
 * | enabled: true (default) | Visible   | Visible                   | Visible          | Visible                 |
 * | enabled: false          | Hidden    | Hidden                    | Hidden           | Visible                 |
 *
 * IMPORTANT: On localhost domain (window.location.hostname), ALL features with requirement
 * flags are hidden by default. Press Ctrl+Shift+E to reveal them all. This ensures a clean
 * "off by default" state during development.
 *
 * NOTE: "Localhost Domain" means running on localhost:#### (checked via window.location.hostname).
 *       Features with requiresLocalhost are hidden even when connected to localhost API,
 *       until you explicitly enable localhost mode with Ctrl+Shift+E.
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
 *   - No additional UI banner is shown; features simply unlock
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
 *   - Example: ceph, queue
 *
 * requiresPowerMode?: boolean
 *   - Feature revealed by Ctrl+Shift+E on production domains
 *   - Use for advanced admin tools that should be accessible in production
 *   - Example: organizationSettings
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
 * if (featureFlags.isEnabled('ceph')) {
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
 * organizationSettings: {
 *   requiresPowerMode: true,
 *   description: 'Organization settings menu item'
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

import { apiConnectionService } from '@/services/api';
import { DEFAULTS } from '@rediacc/shared/config';

export interface FeatureFlag {
  enabled?: boolean; // If not specified, defaults to true. Only use false for truly disabled/deprecated features
  requiresLocalhost?: boolean; // Only show when connected to localhost
  requiresBuildType?: 'DEBUG' | 'RELEASE'; // Only show in specific build type
  requiresExpertMode?: boolean; // Requires expert UI mode (checked separately in components)
  requiresPowerMode?: boolean; // Can be revealed via keyboard shortcuts (session-only)
  localhostOnly?: boolean; // Automatically enable when running on localhost domain (ignores other requirement flags)
  description?: string; // Description of the feature
}

class FeatureFlags {
  private isDevelopment = false;
  private isPowerModeActive = false; // Global power mode state (session-only)
  private isLocalhostModeActive = false; // Localhost mode state (session-only)
  private readonly listeners: Set<() => void> = new Set();

  constructor() {
    // Will be initialized after API connection is established
  }

  /**
   * Check if running on localhost domain
   * @returns true if hostname is localhost or 127.0.0.1
   */
  private isRunningOnLocalhost(): boolean {
    if (typeof window === 'undefined') return false;
    const hostname = window.location.hostname;
    return hostname === 'localhost' || hostname === '127.0.0.1';
  }

  /**
   * Define all feature flags here
   * This is the single source of truth for all beta features
   */
  private readonly flags: Record<string, FeatureFlag> = {
    // Ceph Storage - Disabled
    ceph: {
      enabled: false,
      description:
        'Ceph storage cluster management - allows creating and managing storage clusters',
    },

    // Plugins - Beta feature (vault-based plugin containers)
    plugins: {
      requiresLocalhost: true, // Hide in production builds
      description: 'Plugin containers system - vault-based feature for custom service containers',
    },

    // Queue Management - Expert mode feature
    queueManagement: {
      requiresExpertMode: true,
      description: 'Queue page for viewing and managing task queues',
    },

    // Audit Logs - Expert mode feature
    auditLogs: {
      requiresExpertMode: true,
      description: 'Audit logs page for viewing system activity and changes',
    },

    // Vault Version Columns - Power mode feature
    vaultVersionColumns: {
      requiresPowerMode: true,
      description: 'Show vault version columns in resource tables for debugging purposes',
    },

    // Advanced Vault Editor - Power mode feature
    advancedVaultEditor: {
      requiresPowerMode: true,
      description: 'Raw JSON editor panel in vault editor - advanced/dangerous feature',
    },

    // Regions & Infrastructure - Expert mode feature
    regionsInfrastructure: {
      requiresExpertMode: true,
      description: 'Regions and infrastructure management section in System page',
    },

    // Danger Zone - Power mode feature
    dangerZone: {
      requiresPowerMode: true,
      description:
        'Danger Zone section including block users, export/import data, and encryption settings',
    },

    // Bridge UI - Split into view (enabled) and manage (disabled)
    // bridgeViewEnabled: Always show bridge info (count, assignments) for transparency
    bridgeViewEnabled: {
      description:
        'Show read-only bridge information (counts, assignments, auto-selected bridge info)',
    },
    // bridgeManageEnabled: Control bridge create/edit/delete UI
    bridgeManageEnabled: {
      description:
        'Show bridge management UI (create, edit, delete bridges in Infrastructure page)',
    },

    // Organization Vault Configuration - Power mode feature
    organizationVaultConfiguration: {
      requiresPowerMode: true,
      description: 'Configure Vault button in Organization Settings section',
    },

    // Personal Vault Configuration - Power mode feature
    personalVaultConfiguration: {
      requiresPowerMode: true,
      description: 'Configure Vault button in Personal Settings section',
    },

    // Organization Settings - Power mode feature
    organizationSettings: {
      requiresPowerMode: true,
      description: 'Organization Settings menu item in Settings navigation',
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
  };

  /**
   * Check basic flag requirements (explicit disable, localhost-only)
   */
  private checkBasicRequirements(flag: FeatureFlag, onLocalhost: boolean): boolean | null {
    // Feature is explicitly disabled (enabled: false)
    if (flag.enabled === false) return false;
    // Localhost-only feature check
    if (flag.localhostOnly) return onLocalhost;
    return null; // Continue checking
  }

  /**
   * Check if feature is hidden on localhost (when mode not active)
   */
  private checkLocalhostHiddenFeatures(flag: FeatureFlag, onLocalhost: boolean): boolean | null {
    if (!onLocalhost) return null;
    // Hide features with requirement flags until Ctrl+Shift+E is pressed
    if (flag.requiresLocalhost || flag.requiresPowerMode || flag.requiresExpertMode) {
      return false;
    }
    return true; // Production features show on localhost
  }

  /**
   * Check feature requirements on non-localhost domains
   */
  private checkNonLocalhostRequirements(flag: FeatureFlag): boolean {
    if (flag.requiresPowerMode && !this.isPowerModeActive) return false;
    if (flag.requiresLocalhost && !this.isDevelopment) return false;
    if (flag.requiresBuildType) {
      const currentBuildType =
        (import.meta.env.VITE_BUILD_TYPE as string | undefined) ?? DEFAULTS.EDITION.BUILD_TYPE;
      if (currentBuildType !== flag.requiresBuildType) return false;
    }
    return true;
  }

  /**
   * Check if a feature is enabled
   * @param featureName - The name of the feature to check
   * @returns true if the feature should be visible/enabled
   */
  isEnabled(featureName: string): boolean {
    const flag = this.flags[featureName] as FeatureFlag | undefined;
    if (flag === undefined) return false;

    const onLocalhost = this.isRunningOnLocalhost();

    // Localhost mode: Enable ALL features when active
    if (onLocalhost && this.isLocalhostModeActive) return true;

    // Check basic requirements
    const basicResult = this.checkBasicRequirements(flag, onLocalhost);
    if (basicResult !== null) return basicResult;

    // Check localhost-specific hiding
    const localhostResult = this.checkLocalhostHiddenFeatures(flag, onLocalhost);
    if (localhostResult !== null) return localhostResult;

    // Check non-localhost requirements
    return this.checkNonLocalhostRequirements(flag);
  }

  /**
   * Get all enabled features
   * @returns Array of enabled feature names
   */
  getEnabledFeatures(): string[] {
    return Object.keys(this.flags).filter((name) => this.isEnabled(name));
  }

  /**
   * Get feature flag details
   * @param featureName - The name of the feature
   * @returns The feature flag configuration or undefined
   */
  getFeature(featureName: string): FeatureFlag | undefined {
    return this.flags[featureName];
  }

  /**
   * Update development state based on current API connection
   * This should be called after API connection is established
   */
  updateDevelopmentState(): void {
    const endpointInfo = apiConnectionService.getEndpointInfo();
    this.isDevelopment = endpointInfo?.type === 'localhost';

    if (import.meta.env.DEV) {
      console.warn('[FeatureFlags] Development state updated:', {
        isDevelopment: this.isDevelopment,
        endpointType: endpointInfo?.type,
        buildType: import.meta.env.VITE_BUILD_TYPE,
        enabledFeatures: this.getEnabledFeatures(),
      });
    }

    this.notifyListeners();
  }

  /**
   * Get development state
   * @returns true if connected to localhost
   */
  isDevelopmentMode(): boolean {
    return this.isDevelopment;
  }

  /**
   * Get current build type
   * @returns 'DEBUG' or 'RELEASE'
   */
  getBuildType(): 'DEBUG' | 'RELEASE' {
    const buildType =
      (import.meta.env.VITE_BUILD_TYPE as string | undefined) ?? DEFAULTS.EDITION.BUILD_TYPE;
    return buildType === 'RELEASE' ? 'RELEASE' : 'DEBUG';
  }

  /**
   * Toggle global power mode (session-only, not persisted)
   * On localhost domain, this toggles localhost mode (enables ALL features)
   * On non-localhost domains, this toggles power mode (enables only power mode features)
   * @returns The new mode state after toggle
   */
  togglePowerMode(): boolean {
    const onLocalhost = this.isRunningOnLocalhost();

    if (onLocalhost) {
      // Toggle localhost mode
      this.isLocalhostModeActive = !this.isLocalhostModeActive;

      if (import.meta.env.DEV) {
        console.warn(
          `[LocalhostMode] Localhost mode ${this.isLocalhostModeActive ? 'enabled' : 'disabled'}`
        );
      }

      this.notifyListeners();
      return this.isLocalhostModeActive;
    }
    // Toggle power mode (original behavior)
    this.isPowerModeActive = !this.isPowerModeActive;

    if (import.meta.env.DEV) {
      console.warn(
        `[PowerMode] Global power mode ${this.isPowerModeActive ? 'enabled' : 'disabled'}`
      );
    }

    this.notifyListeners();
    return this.isPowerModeActive;
  }

  /**
   * Enable global power mode (session-only, not persisted)
   */
  enablePowerMode(): void {
    this.isPowerModeActive = true;

    if (import.meta.env.DEV) {
      console.warn('[PowerMode] Global power mode enabled');
    }

    this.notifyListeners();
  }

  /**
   * Check if global power mode is enabled
   * @returns true if power mode is active
   */
  isPowerModeEnabled(): boolean {
    return this.isPowerModeActive;
  }

  /**
   * Check if localhost mode is enabled
   * @returns true if localhost mode is active
   */
  isLocalhostModeEnabled(): boolean {
    return this.isLocalhostModeActive;
  }

  /**
   * Subscribe to feature flag changes (power/localhost mode toggles, development state updates).
   * Returns an unsubscribe function.
   */
  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notifyListeners(): void {
    this.listeners.forEach((listener) => {
      try {
        listener();
      } catch (error) {
        console.error('[FeatureFlags] Listener error', error);
      }
    });
  }
}

// Export singleton instance
export const featureFlags = new FeatureFlags();
