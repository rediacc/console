import { configService } from '@/services/configService'
import { apiClient } from './client'

export async function initializeApiClient() {
  try {
    // Get the API URL from config service
    const apiUrl = await configService.getApiUrl()
    
    // Update the API client with the correct URL
    apiClient.updateApiUrl(apiUrl)
  } catch (error) {
    // Will use default URL from environment or hardcoded fallback
  }
}