/**
 * API Constants
 * Centralized constants for external API endpoints and configuration URLs
 */

/**
 * Get JSON API base URL based on runtime config or environment
 *
 * Priority:
 * 1. Runtime config (window.REDIACC_CONFIG.jsonUrl) - for intranet deployments
 * 2. Production: relative path '/json' (works for www.rediacc.com and Docker)
 * 3. Development: www.rediacc.com/json
 *
 * @returns The base URL for JSON configuration files
 */
function getJsonApiBaseUrl(): string {
  // Runtime config takes precedence (intranet deployment)
  if (typeof window !== 'undefined' && window.REDIACC_CONFIG?.jsonUrl) {
    return window.REDIACC_CONFIG.jsonUrl;
  }

  // In production, use relative path (works for both www.rediacc.com and intranet)
  if (import.meta.env.PROD) {
    return '/json';
  }

  // In development, use www.rediacc.com
  return 'https://www.rediacc.com/json';
}

/**
 * Get configuration URLs with dynamic base URL
 * Note: These are getters to ensure the base URL is evaluated at call time
 */
export const CONFIG_URLS = {
  /** Templates list endpoint */
  get TEMPLATES(): string {
    return `${getJsonApiBaseUrl()}/templates.json`;
  },

  /** Templates directory (for individual template JSON files) */
  get TEMPLATES_DIR(): string {
    return `${getJsonApiBaseUrl()}/templates`;
  },

  /** API endpoints configuration */
  get ENDPOINTS(): string {
    return `${getJsonApiBaseUrl()}/configs/endpoints.json`;
  },

  /** Services configuration */
  get SERVICES(): string {
    return `${getJsonApiBaseUrl()}/configs/services.json`;
  },

  /** Tiers configuration */
  get TIERS(): string {
    return `${getJsonApiBaseUrl()}/configs/tiers.json`;
  },
} as const;
