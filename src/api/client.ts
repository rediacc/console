import axios, { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { store } from '@/store/store'
import { logout } from '@/store/auth/authSlice'
import { showMessage } from '@/utils/messages'
import { encryptRequestData, decryptResponseData, hasVaultFields } from './encryptionMiddleware'
import { tokenService } from '@/services/tokenService'

// API configuration
const API_PREFIX = '/StoredProcedure'

// Get API URL - will be set dynamically
let API_BASE_URL = import.meta.env.VITE_API_URL || 
  (import.meta.env.PROD ? '/api' : 'http://localhost:7322/api')

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
    this.client.interceptors.request.use(
      async (config: InternalAxiosRequestConfig) => {
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
        const responseData = await this.handleResponseDecryption(response.data as ApiResponse)
        response.data = responseData

        if (responseData.failure !== 0) return this.handleApiFailure(responseData)
        
        await this.handleTokenRotation(responseData)
        return response
      },
      (error) => this.handleResponseError(error)
    )
  }

  async login(email: string, passwordHash: string, sessionName = 'Web Session') {
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

  async activateUser(email: string, activationCode: string) {
    return this.makeRequest('/ActivateUserAccount', { userEmail: email, activationCode })
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
      response?.data?.tables?.[0]?.data?.[0]?.message,
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
    const newToken = responseData.tables?.[0]?.data?.[0]?.nextRequestCredential
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