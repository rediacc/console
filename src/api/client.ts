import axios, { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { store } from '@/store/store'
import { logout } from '@/store/auth/authSlice'
import { showMessage } from '@/utils/messages'
import { encryptRequestData, decryptResponseData, hasVaultFields } from './encryptionMiddleware'
import { tokenService } from '@/services/tokenService'

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

  // HTTP status codes
  private readonly HTTP_UNAUTHORIZED = 401
  private readonly HTTP_SERVER_ERROR = 500
  
  // Timing constants
  private readonly TOKEN_UPDATE_DELAY_MS = 5
  private readonly TOKEN_UPDATE_POLL_INTERVAL_MS = 10
  private readonly REDIRECT_DELAY_MS = 1500

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
        // Get token from secure storage instead of Redux state
        const token = await tokenService.getToken()

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
        let responseData = response.data as ApiResponse

        // Decrypt vault fields in response data if master password is set
        responseData = await this.handleResponseDecryption(responseData)
        response.data = responseData

        // Check for API-level failure
        if (responseData.failure !== 0) {
          return this.handleApiFailure(responseData)
        }

        // Handle token rotation with lock to prevent race conditions
        await this.handleTokenRotation(responseData)

        return response
      },
      (error) => this.handleResponseError(error)
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
      await this.waitForTokenUpdate()
      
      const response = await request()
      return response.data
    }

    // Add to queue and wait for previous requests to complete
    this.requestQueue = this.requestQueue
      .then(executeRequest)
      .catch(executeRequest) // Continue queue even if previous request failed

    return this.requestQueue
  }

  private async waitForTokenUpdate(): Promise<void> {
    while (this.isUpdatingToken) {
      await new Promise(resolve => setTimeout(resolve, this.TOKEN_UPDATE_POLL_INTERVAL_MS))
    }
  }

  private async handleResponseDecryption(responseData: ApiResponse): Promise<ApiResponse> {
    if (responseData && hasVaultFields(responseData)) {
      try {
        return await decryptResponseData(responseData)
      } catch (error) {
        // Decryption errors are handled in middleware (shows toast)
        // Continue with encrypted data
        return responseData
      }
    }
    return responseData
  }

  private handleApiFailure(responseData: ApiResponse): Promise<never> {
    if (responseData.failure === this.HTTP_UNAUTHORIZED) {
      this.handleUnauthorizedError()
      return Promise.reject(new Error('Unauthorized'))
    }
    
    const errorMessage = responseData.errors?.join('; ') || responseData.message || 'Request failed'
    return Promise.reject(new Error(errorMessage))
  }

  private handleUnauthorizedError(): void {
    showMessage('error', 'Session expired. Please login again.')
    store.dispatch(logout())
    this.redirectToLogin()
  }

  private async handleTokenRotation(responseData: ApiResponse): Promise<void> {
    const newToken = responseData.tables?.[0]?.data?.[0]?.nextRequestCredential
    
    if (newToken) {
      this.isUpdatingToken = true
      try {
        await tokenService.updateToken(newToken)
        // Small delay to ensure token is updated
        await new Promise(resolve => setTimeout(resolve, this.TOKEN_UPDATE_DELAY_MS))
      } finally {
        this.isUpdatingToken = false
      }
    }
  }

  private handleResponseError(error: any): Promise<never> {
    // First, check if the response has our API error structure with "errors" array
    if (error.response?.data) {
      const apiResponse = error.response.data as ApiResponse
      if (apiResponse.errors && apiResponse.errors.length > 0) {
        const errorMessage = apiResponse.errors.join('; ')
        const customError = new Error(errorMessage)
        ;(customError as any).response = error.response
        return Promise.reject(customError)
      }
    }

    // Handle specific status codes
    if (error.response?.status === this.HTTP_UNAUTHORIZED) {
      this.handleUnauthorizedResponseError(error.response)
    } else if (error.response?.status >= this.HTTP_SERVER_ERROR) {
      showMessage('error', 'Server error. Please try again later.')
    } else if (error.request && !error.response) {
      showMessage('error', 'Network error. Please check your connection.')
    }
    
    return Promise.reject(error)
  }

  private handleUnauthorizedResponseError(response: any): void {
    const errorMessage = response?.data?.tables?.[0]?.data?.[0]?.message
    if (errorMessage?.includes('Invalid request credential')) {
      showMessage('error', 'Session expired. Please login again.')
    }
    store.dispatch(logout())
    this.redirectToLogin()
  }

  private redirectToLogin(): void {
    const currentPath = window.location.pathname
    const basePath = import.meta.env.BASE_URL || '/'
    const loginPath = `${basePath}login`.replace('//', '/')
    
    if (!currentPath.includes('/login')) {
      setTimeout(() => {
        window.location.href = loginPath
      }, this.REDIRECT_DELAY_MS)
    }
  }
}

export const apiClient = new ApiClient()
export default apiClient