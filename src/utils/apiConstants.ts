/**
 * API Constants
 * Centralized constants for external API endpoints and configuration URLs
 */

/**
 * Base URL for JSON configuration files hosted on json.rediacc.com
 * Uses absolute URLs with proper fetch options to avoid CORS preflight issues
 */
export const JSON_API_BASE_URL = 'https://json.rediacc.com'

/**
 * Configuration endpoints - direct absolute URLs to json.rediacc.com
 * Note: templates.json is at root, other configs are in /configs/ directory
 */
export const CONFIG_URLS = {
  /** Templates list endpoint */
  TEMPLATES: `${JSON_API_BASE_URL}/templates.json`,

  /** Templates directory (for individual template JSON files) */
  TEMPLATES_DIR: `${JSON_API_BASE_URL}/templates`,

  /** API endpoints configuration */
  ENDPOINTS: `${JSON_API_BASE_URL}/configs/endpoints.json`,

  /** Pricing configuration */
  PRICING: `${JSON_API_BASE_URL}/configs/pricing.json`,

  /** Services configuration */
  SERVICES: `${JSON_API_BASE_URL}/configs/services.json`,

  /** Tiers configuration */
  TIERS: `${JSON_API_BASE_URL}/configs/tiers.json`,
} as const
