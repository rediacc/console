/**
 * Endpoint Service
 * Manages API endpoint selection with predefined and custom endpoints
 */

import { CONFIG_URLS } from '@/utils/apiConstants';

export interface Endpoint {
  id: string;
  name: string;
  url: string;
  type: string; // Flexible type: 'production', 'sandbox', 'localhost', 'custom', 'us', 'eu', etc.
  description?: string;
  icon?: string;
}

interface EndpointsManifest {
  endpoints: Endpoint[];
}

const STORAGE_KEY_SELECTED = 'rediacc_selected_endpoint';
const STORAGE_KEY_CUSTOM = 'rediacc_custom_endpoints';

class EndpointService {
  private endpointsCache: Endpoint[] | null = null;
  private fetchPromise: Promise<Endpoint[]> | null = null;

  /**
   * Fetch predefined endpoints from endpoints.json
   */
  private async fetchPredefinedEndpoints(): Promise<Endpoint[]> {
    try {
      // Use simple CORS request (no preflight needed)
      const response = await fetch(CONFIG_URLS.ENDPOINTS, {
        method: 'GET',
        mode: 'cors',
        credentials: 'omit',
        cache: 'default',
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch endpoints.json: ${response.status}`);
      }

      const data = (await response.json()) as EndpointsManifest;

      if (!Array.isArray(data.endpoints)) {
        throw new Error('endpoints.json has invalid structure');
      }

      return data.endpoints;
    } catch (error) {
      console.warn('Failed to fetch endpoints.json, using fallback', error);

      // Fallback to default endpoints
      return [
        {
          id: 'production',
          name: 'Production',
          url: 'https://www.rediacc.com/api',
          type: 'production',
          description: 'Main production environment',
          icon: '🌐',
        },
        {
          id: 'sandbox',
          name: 'Sandbox',
          url: 'https://sandbox.rediacc.com/api',
          type: 'sandbox',
          description: 'Testing and development sandbox',
          icon: '🏖️',
        },
        {
          id: 'localhost',
          name: 'Local Development',
          url: 'http://localhost:7322/api',
          type: 'localhost',
          description: 'Local development environment',
          icon: '💻',
        },
      ];
    }
  }

  /**
   * Get custom endpoints from localStorage
   */
  private getCustomEndpoints(): Endpoint[] {
    try {
      const stored = localStorage.getItem(STORAGE_KEY_CUSTOM);
      if (!stored) return [];

      const custom = JSON.parse(stored);
      return Array.isArray(custom) ? custom : [];
    } catch (error) {
      console.warn('Failed to parse custom endpoints from localStorage', error);
      return [];
    }
  }

  /**
   * Save custom endpoints to localStorage
   */
  private saveCustomEndpoints(endpoints: Endpoint[]): void {
    try {
      localStorage.setItem(STORAGE_KEY_CUSTOM, JSON.stringify(endpoints));
    } catch (error) {
      console.error('Failed to save custom endpoints to localStorage', error);
    }
  }

  /**
   * Fetch all endpoints (predefined + custom)
   * Uses cache to avoid repeated fetches
   */
  async fetchEndpoints(forceRefresh = false): Promise<Endpoint[]> {
    if (this.endpointsCache && !forceRefresh) {
      return [...this.endpointsCache, ...this.getCustomEndpoints()];
    }

    // Return existing fetch promise if already fetching
    if (this.fetchPromise) {
      const predefined = await this.fetchPromise;
      return [...predefined, ...this.getCustomEndpoints()];
    }

    // Create new fetch promise
    this.fetchPromise = this.fetchPredefinedEndpoints();

    try {
      this.endpointsCache = await this.fetchPromise;
      return [...this.endpointsCache, ...this.getCustomEndpoints()];
    } finally {
      this.fetchPromise = null;
    }
  }

  /**
   * Get the selected endpoint from localStorage
   */
  getSelectedEndpoint(): Endpoint | null {
    try {
      const stored = localStorage.getItem(STORAGE_KEY_SELECTED);
      if (!stored) return null;

      return JSON.parse(stored) as Endpoint;
    } catch (error) {
      console.warn('Failed to parse selected endpoint from localStorage', error);
      return null;
    }
  }

  /**
   * Set the selected endpoint in localStorage
   */
  setSelectedEndpoint(endpoint: Endpoint): void {
    try {
      localStorage.setItem(STORAGE_KEY_SELECTED, JSON.stringify(endpoint));
    } catch (error) {
      console.error('Failed to save selected endpoint to localStorage', error);
    }
  }

  /**
   * Clear the selected endpoint
   */
  clearSelectedEndpoint(): void {
    try {
      localStorage.removeItem(STORAGE_KEY_SELECTED);
    } catch (error) {
      console.error('Failed to clear selected endpoint from localStorage', error);
    }
  }

  /**
   * Add a custom endpoint
   */
  addCustomEndpoint(name: string, url: string): Endpoint {
    // Validate URL
    try {
      new URL(url);
    } catch {
      throw new Error('Invalid URL format');
    }

    // Ensure URL ends with /api
    const normalizedUrl = url.endsWith('/api') ? url : `${url}/api`;

    const customEndpoint: Endpoint = {
      id: `custom-${Date.now()}`,
      name,
      url: normalizedUrl,
      type: 'custom',
      description: 'Custom endpoint',
      icon: '⚙️',
    };

    const customEndpoints = this.getCustomEndpoints();
    customEndpoints.push(customEndpoint);
    this.saveCustomEndpoints(customEndpoints);

    return customEndpoint;
  }

  /**
   * Remove a custom endpoint
   */
  removeCustomEndpoint(id: string): void {
    const customEndpoints = this.getCustomEndpoints();
    const filtered = customEndpoints.filter((e) => e.id !== id);
    this.saveCustomEndpoints(filtered);

    // If the removed endpoint was selected, clear selection
    const selected = this.getSelectedEndpoint();
    if (selected?.id === id) {
      this.clearSelectedEndpoint();
    }
  }

  /**
   * Find endpoint by ID
   */
  async findEndpointById(id: string): Promise<Endpoint | null> {
    const endpoints = await this.fetchEndpoints();
    return endpoints.find((e) => e.id === id) ?? null;
  }

  /**
   * Check if running on localhost
   */
  isLocalhost(): boolean {
    return window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  }

  /**
   * Clear cache (useful for testing)
   */
  clearCache(): void {
    this.endpointsCache = null;
    this.fetchPromise = null;
  }
}

export const endpointService = new EndpointService();
