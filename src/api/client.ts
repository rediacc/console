import axios, { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios'

// Extend axios config to include metadata
declare module 'axios' {
  interface InternalAxiosRequestConfig {
    metadata?: {
      startTime: number
    }
  }
}
import { store } from '@/store/store'
import { logout } from '@/store/auth/authSlice'
import { showMessage } from '@/utils/messages'
import { encryptRequestData, decryptResponseData, hasVaultFields } from './encryptionMiddleware'
import { tokenService } from '@/services/tokenService'
import { apiConnectionService } from '@/services/apiConnectionService'
import { telemetryService } from '@/services/telemetryService'

// API configuration
const API_PREFIX = '/StoredProcedure'

// API URL will be determined dynamically based on connection health check
let API_BASE_URL = ''

export interface ApiResponse<T = any> {
  failure: number
  errors: string[]
  message: string
  resultSets: Array<{
    data: T[]
  }>
}

class ApiClient {
  private client: AxiosInstance
  private requestQueue: Promise<any> = Promise.resolve()
  private isUpdatingToken = false

  private readonly HTTP_UNAUTHORIZED = 401
  private readonly HTTP_SERVER_ERROR = 500
  private readonly TOKEN_UPDATE_DELAY_MS = 5

  // Method to update API URL dynamically
  updateApiUrl(newUrl: string) {
    API_BASE_URL = newUrl
    this.client.defaults.baseURL = API_BASE_URL + API_PREFIX
  }
  private readonly TOKEN_UPDATE_POLL_INTERVAL_MS = 10
  private readonly REDIRECT_DELAY_MS = 1500

  constructor() {
    // Initialize with empty baseURL, will be set after health check
    this.client = axios.create({
      baseURL: '',
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    this.setupInterceptors()
    this.initializeBaseUrl()
  }

  private async initializeBaseUrl() {
    // Get the API URL from connection service (will perform health check if needed)
    const apiUrl = await apiConnectionService.getApiUrl()
    API_BASE_URL = apiUrl
    this.client.defaults.baseURL = `${API_BASE_URL}${API_PREFIX}`
  }

  private setupInterceptors() {
    this.client.interceptors.request.use(
      async (config: InternalAxiosRequestConfig) => {
        // Add request start time for telemetry
        config.metadata = { startTime: performance.now() }

        const token = await tokenService.getToken()
        if (token) config.headers['Rediacc-RequestToken'] = token

        if (config.data && hasVaultFields(config.data)) {
          try {
            config.data = await encryptRequestData(config.data)
          } catch (error) {
            return Promise.reject(error)
          }
        }
        return config
      }
    )

    this.client.interceptors.response.use(
      async (response) => {
        const startTime = response.config.metadata?.startTime || 0
        const duration = performance.now() - startTime

        const responseData = await this.handleResponseDecryption(response.data as ApiResponse)
        response.data = responseData

        // Track successful API call
        telemetryService.trackApiCall(
          response.config.method?.toUpperCase() || 'UNKNOWN',
          response.config.url || '',
          response.status,
          duration
        )

        if (responseData.failure !== 0) return this.handleApiFailure(responseData)

        await this.handleTokenRotation(responseData)
        return response
      },
      (error) => {
        const startTime = error.config?.metadata?.startTime || 0
        const duration = performance.now() - startTime

        // Track failed API call
        telemetryService.trackApiCall(
          error.config?.method?.toUpperCase() || 'UNKNOWN',
          error.config?.url || '',
          error.response?.status,
          duration,
          error.message
        )

        return this.handleResponseError(error)
      }
    )
  }

  async login(email: string, passwordHash: string, sessionName = 'Web Session') {
    // Ensure API URL is initialized before login
    if (!API_BASE_URL) {
      await this.initializeBaseUrl()
    }
    
    const response = await axios.post<ApiResponse>(
      `${API_BASE_URL}${API_PREFIX}/CreateAuthenticationRequest`,
      { name: sessionName },
      { headers: { 'Rediacc-UserEmail': email, 'Rediacc-UserHash': passwordHash } }
    )
    return response.data
  }

  async logout() {
    return (await this.client.post<ApiResponse>('/DeleteUserRequest', {})).data
  }

  async activateUser(email: string, activationCode: string, passwordHash: string) {
    const response = await this.client.post<ApiResponse>('/ActivateUserAccount', 
      { activationCode },
      { headers: { 
        'Rediacc-UserEmail': email,
        'Rediacc-UserHash': passwordHash 
      } }
    )
    return response.data
  }

  private async makeRequest<T = any>(endpoint: string, data?: any): Promise<ApiResponse<T>> {
    return this.queueRequest(() => this.client.post<ApiResponse<T>>(endpoint, data || {}))
  }

  get = <T = any>(endpoint: string, params?: any): Promise<ApiResponse<T>> => 
    this.makeRequest<T>(endpoint, params)

  post = <T = any>(endpoint: string, data: any): Promise<ApiResponse<T>> => 
    this.makeRequest<T>(endpoint, data)

  put = <T = any>(endpoint: string, data: any): Promise<ApiResponse<T>> => 
    this.makeRequest<T>(endpoint, data)

  delete = <T = any>(endpoint: string, data: any): Promise<ApiResponse<T>> => 
    this.makeRequest<T>(endpoint, data)

  private async queueRequest<T>(request: () => Promise<AxiosResponse<ApiResponse<T>>>): Promise<ApiResponse<T>> {
    const executeRequest = async () => {
      await this.waitForTokenUpdate()
      return (await request()).data
    }

    this.requestQueue = this.requestQueue.then(executeRequest).catch(executeRequest)
    return this.requestQueue
  }

  private async waitForTokenUpdate(): Promise<void> {
    while (this.isUpdatingToken) {
      await new Promise(resolve => setTimeout(resolve, this.TOKEN_UPDATE_POLL_INTERVAL_MS))
    }
  }

  private async handleResponseDecryption(responseData: ApiResponse): Promise<ApiResponse> {
    if (!responseData || !hasVaultFields(responseData)) return responseData
    try {
      return await decryptResponseData(responseData)
    } catch {
      return responseData
    }
  }

  private extractErrorMessage(error: any): string {
    const { response, errors, message } = error
    return [
      response?.data?.errors?.join('; '),
      response?.data?.message,
      response?.data?.resultSets?.[0]?.data?.[0]?.message,
      errors?.join('; '),
      message,
    ].find(Boolean) || 'Request failed'
  }
  
  private isUnauthorizedError(error: any): boolean {
    return error.failure === this.HTTP_UNAUTHORIZED || error.response?.status === this.HTTP_UNAUTHORIZED
  }
  
  private handleUnauthorizedError(): void {
    showMessage('error', 'Session expired. Please login again.')
    store.dispatch(logout())
    this.redirectToLogin()
  }
  
  private handleApiFailure(responseData: ApiResponse): Promise<never> {
    if (this.isUnauthorizedError(responseData)) {
      this.handleUnauthorizedError()
      return Promise.reject(new Error('Unauthorized'))
    }
    return Promise.reject(new Error(this.extractErrorMessage(responseData)))
  }

  private async handleTokenRotation(responseData: ApiResponse): Promise<void> {
    const newToken = responseData.resultSets?.[0]?.data?.[0]?.nextRequestToken
    if (!newToken) return
    
    this.isUpdatingToken = true
    try {
      await tokenService.updateToken(newToken)
      await new Promise(resolve => setTimeout(resolve, this.TOKEN_UPDATE_DELAY_MS))
    } finally {
      this.isUpdatingToken = false
    }
  }

  private handleResponseError(error: any): Promise<never> {
    const errorHandlers = {
      [this.isUnauthorizedError(error) ? 'unauthorized' : '']: () => this.handleUnauthorizedError(),
      [error.response?.status >= this.HTTP_SERVER_ERROR ? 'server' : '']: () => 
        showMessage('error', 'Server error. Please try again later.'),
      [error.request && !error.response ? 'network' : '']: () => 
        showMessage('error', 'Network error. Please check your connection.')
    }
    
    Object.entries(errorHandlers).forEach(([key, handler]) => key && handler())
    
    const customError = new Error(this.extractErrorMessage(error))
    ;(customError as any).response = error.response
    return Promise.reject(customError)
  }

  private redirectToLogin(): void {
    const { pathname } = window.location
    const basePath = import.meta.env.BASE_URL || '/'
    const loginPath = `${basePath}login`.replace('//', '/')
    
    if (!pathname.includes('/login')) {
      setTimeout(() => window.location.href = loginPath, this.REDIRECT_DELAY_MS)
    }
  }
}

export const apiClient = new ApiClient()
export default apiClient