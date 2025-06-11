import axios, { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { store } from '@/store/store'
import { updateToken, logout } from '@/store/auth/authSlice'
import { showMessage } from '@/utils/messages'
import { encryptRequestData, decryptResponseData, hasVaultFields } from './encryptionMiddleware'

// Use relative path in production (served via nginx proxy) and absolute in development
const MIDDLEWARE_PORT = import.meta.env.VITE_MIDDLEWARE_PORT || '8080'
const API_BASE_URL = import.meta.env.VITE_API_URL || 
  (import.meta.env.PROD ? '/api' : `http://localhost:${MIDDLEWARE_PORT}/api`)
const API_PREFIX = '/StoredProcedure'

export interface ApiResponse<T = any> {
  failure: number
  errors: string[]
  message: string
  tables: Array<{
    data: T[]
  }>
}

class ApiClient {
  private client: AxiosInstance
  private requestQueue: Promise<any> = Promise.resolve()
  private isUpdatingToken = false

  constructor() {
    this.client = axios.create({
      baseURL: `${API_BASE_URL}${API_PREFIX}`,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    this.setupInterceptors()
  }

  private setupInterceptors() {
    // Request interceptor to add auth token and encrypt vault fields
    this.client.interceptors.request.use(
      async (config: InternalAxiosRequestConfig) => {
        const state = store.getState()
        const token = state.auth.token

        if (token) {
          config.headers['Rediacc-RequestToken'] = token
        }

        // Encrypt vault fields in request data if master password is set
        if (config.data && hasVaultFields(config.data)) {
          try {
            config.data = await encryptRequestData(config.data)
          } catch (error) {
            // If encryption fails, the middleware will show error toast
            return Promise.reject(error)
          }
        }

        return config
      },
      (error) => {
        return Promise.reject(error)
      }
    )

    // Response interceptor for token rotation, decryption, and error handling
    this.client.interceptors.response.use(
      async (response) => {
        let data = response.data as ApiResponse

        // Decrypt vault fields in response data if master password is set
        if (data && hasVaultFields(data)) {
          try {
            data = await decryptResponseData(data)
            response.data = data
          } catch (error) {
            // Decryption errors are handled in middleware (shows toast)
            // Continue with encrypted data
          }
        }

        // Check for API-level failure
        if (data.failure !== 0) {
          // Check if failure code is 401 (unauthorized)
          if (data.failure === 401) {
            // Handle as unauthorized - same as HTTP 401
            showMessage('error', 'Session expired. Please login again.')
            store.dispatch(logout())
            
            // Only redirect if not already on login page
            const currentPath = window.location.pathname
            const basePath = import.meta.env.BASE_URL || '/'
            const loginPath = `${basePath}login`.replace('//', '/')
            
            if (!currentPath.includes('/login')) {
              // Delay redirect so user can see the message
              setTimeout(() => {
                window.location.href = loginPath
              }, 1500) // 1.5 second delay
            }
            return Promise.reject(new Error('Unauthorized'))
          }
          
          const errorMessage = data.errors?.join('; ') || data.message || 'Request failed'
          // Don't show message here - let the mutation handler show it
          // This prevents duplicate messages and allows mutation handlers to customize error display
          return Promise.reject(new Error(errorMessage))
        }

        // Handle token rotation with lock to prevent race conditions
        if (data.tables?.[0]?.data?.[0]?.nextRequestCredential) {
          this.isUpdatingToken = true
          try {
            const newToken = data.tables[0].data[0].nextRequestCredential
            store.dispatch(updateToken(newToken))
            // Small delay to ensure Redux state is updated
            await new Promise(resolve => setTimeout(resolve, 5))
          } finally {
            this.isUpdatingToken = false
          }
        }

        return response
      },
      (error) => {
        // First, check if the response has our API error structure with "errors" array
        if (error.response?.data) {
          const apiResponse = error.response.data as ApiResponse
          if (apiResponse.errors && apiResponse.errors.length > 0) {
            // Create a new error with the API error message
            const errorMessage = apiResponse.errors.join('; ')
            const customError = new Error(errorMessage)
            // Copy over the response data
            ;(customError as any).response = error.response
            return Promise.reject(customError)
          }
        }

        // Handle specific status codes
        if (error.response?.status === 401) {
          // Check if it's specifically a validation error on page refresh
          const errorMessage = error.response?.data?.tables?.[0]?.data?.[0]?.message
          if (errorMessage?.includes('Invalid request credential')) {
            // Only show this message once, not for each failed request
            showMessage('error', 'Session expired. Please login again.')
          }
          store.dispatch(logout())
          
          // Only redirect if not already on login page
          const currentPath = window.location.pathname
          const basePath = import.meta.env.BASE_URL || '/'
          const loginPath = `${basePath}login`.replace('//', '/')
          
          if (!currentPath.includes('/login')) {
            // Delay redirect so user can see the message
            setTimeout(() => {
              window.location.href = loginPath
            }, 1500) // 1.5 second delay
          }
        } else if (error.response?.status >= 500) {
          showMessage('error', 'Server error. Please try again later.')
        } else if (error.request && !error.response) {
          // Only show network error if there's truly no response
          showMessage('error', 'Network error. Please check your connection.')
        }
        
        // For other errors, pass them through as-is
        return Promise.reject(error)
      }
    )
  }

  // Auth endpoints
  async login(email: string, passwordHash: string, sessionName: string = 'Web Session') {
    const response = await axios.post<ApiResponse>(
      `${API_BASE_URL}${API_PREFIX}/CreateAuthenticationRequest`,
      { name: sessionName },
      {
        headers: {
          'Rediacc-UserEmail': email,
          'Rediacc-UserHash': passwordHash,
        },
      }
    )
    return response.data
  }

  async logout() {
    const response = await this.client.post<ApiResponse>('/DeleteUserRequest', {})
    return response.data
  }

  async activateUser(email: string, activationCode: string) {
    const response = await axios.post<ApiResponse>(
      `${API_BASE_URL}${API_PREFIX}/ActivateUserAccount`,
      { userEmail: email, activationCode }
    )
    return response.data
  }

  // Generic API methods with request queuing for token rotation
  async get<T = any>(endpoint: string, params?: any): Promise<ApiResponse<T>> {
    return this.queueRequest(() => this.client.post<ApiResponse<T>>(endpoint, params || {}))
  }

  async post<T = any>(endpoint: string, data: any): Promise<ApiResponse<T>> {
    return this.queueRequest(() => this.client.post<ApiResponse<T>>(endpoint, data))
  }

  async put<T = any>(endpoint: string, data: any): Promise<ApiResponse<T>> {
    return this.queueRequest(() => this.client.post<ApiResponse<T>>(endpoint, data))
  }

  async delete<T = any>(endpoint: string, data: any): Promise<ApiResponse<T>> {
    return this.queueRequest(() => this.client.post<ApiResponse<T>>(endpoint, data))
  }

  private async queueRequest<T>(request: () => Promise<AxiosResponse<ApiResponse<T>>>): Promise<ApiResponse<T>> {
    // Queue requests to prevent race conditions with token rotation
    const executeRequest = async () => {
      // Wait for any token update to complete
      while (this.isUpdatingToken) {
        await new Promise(resolve => setTimeout(resolve, 10))
      }
      
      const response = await request()
      return response.data
    }

    // Add to queue and wait for previous requests to complete
    this.requestQueue = this.requestQueue
      .then(executeRequest)
      .catch(executeRequest) // Continue queue even if previous request failed

    return this.requestQueue
  }
}

export const apiClient = new ApiClient()
export default apiClient