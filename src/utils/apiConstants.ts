/**
 * API Constants
 * Centralized constants for external API endpoints and configuration URLs
 */

/**
 * Check if running in development mode (localhost with Vite proxy)
 */
const isDevelopment =
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'

/**
 * Base URL for JSON configuration files
 * - Development (localhost): Use relative URLs to leverage Vite proxy (avoids CORS preflight)
 * - Production: Use absolute URLs to work correctly through nginx proxy
 */
export const JSON_API_BASE_URL = isDevelopment ? '' : 'https://json.rediacc.com'

/**
 * Configuration endpoints
 * Proxies are necessary because GitHub Pages returns 405 for OPTIONS (CORS preflight).
 * Using proxies makes requests same-origin, avoiding preflight entirely.
 */
export const CONFIG_URLS = {
  /** Templates list endpoint */
  TEMPLATES: `${JSON_API_BASE_URL}/configs/templates.json`,

  /** Templates directory (for individual template JSON files) */
  TEMPLATES_DIR: `${JSON_API_BASE_URL}/configs/templates`,

  /** API endpoints configuration */
  ENDPOINTS: `${JSON_API_BASE_URL}/configs/endpoints.json`,

  /** Pricing configuration */
  PRICING: `${JSON_API_BASE_URL}/configs/pricing.json`,

  /** Services configuration */
  SERVICES: `${JSON_API_BASE_URL}/configs/services.json`,

  /** Tiers configuration */
  TIERS: `${JSON_API_BASE_URL}/configs/tiers.json`,
} as const
