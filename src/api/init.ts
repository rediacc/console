import { configService } from '@/services/configService'
import { apiClient } from './client'

export async function initializeApiClient() {
  try {
    // Get the API URL from config service
    const apiUrl = await configService.getApiUrl()
    
    // Update the API client with the correct URL
    apiClient.updateApiUrl(apiUrl)
    
    console.log('API client initialized with URL:', apiUrl)
  } catch (error) {
    console.error('Failed to initialize API client:', error)
    // Will use default URL from environment or hardcoded fallback
  }
}