import { configService } from '@/services/configService';
import { apiConnectionService } from '@/services/apiConnectionService';
import { apiClient } from './client';

export async function initializeApiClient() {
  try {
    // Perform the startup health check to determine which endpoint to use
    await apiConnectionService.performStartupHealthCheck();

    // Get the API URL from config service (which now uses the selected endpoint)
    const apiUrl = await configService.getApiUrl();

    // Update the API client with the correct URL
    apiClient.updateApiUrl(apiUrl);

    // Log the selected endpoint for debugging
    const endpointInfo = apiConnectionService.getEndpointInfo();
    if (endpointInfo) {
      console.warn(`[API] Connected to: ${endpointInfo.label} (${endpointInfo.url})`);
    }
  } catch (error) {
    console.error('[API] Initialization failed:', error);
    // Will use default URL from environment or hardcoded fallback
  }
}
