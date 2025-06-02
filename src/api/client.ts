import axios, { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { store } from '@/store/store'
import { updateToken, logout } from '@/store/auth/authSlice'
import { showMessage } from '@/utils/messages'

// Use relative path in production (served via nginx proxy) and absolute in development
const API_BASE_URL = import.meta.env.VITE_API_URL || 
  (import.meta.env.PROD ? '/api' : 'http://localhost:8080/api')
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
    // Request interceptor to add auth token
    this.client.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        const state = store.getState()
        const token = state.auth.token

        if (token) {
          config.headers['Rediacc-RequestToken'] = token
        }

        return config
      },
      (error) => {
        return Promise.reject(error)
      }
    )

    // Response interceptor for token rotation and error handling
    this.client.interceptors.response.use(
      async (response) => {
        const data = response.data as ApiResponse

        // Check for API-level failure
        if (data.failure !== 0) {
          const errorMessage = data.errors?.join('; ') || data.message || 'Request failed'
          showMessage('error', errorMessage)
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
        if (error.response?.status === 401) {
          store.dispatch(logout())
          showMessage('error', 'Session expired. Please login again.')
          window.location.href = `${import.meta.env.BASE_URL}login`
        } else if (error.response?.status >= 500) {
          showMessage('error', 'Server error. Please try again later.')
        } else if (error.request) {
          showMessage('error', 'Network error. Please check your connection.')
        }

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

  async getCompany(email: string, passwordHash: string) {
    const response = await axios.post<ApiResponse>(
      `${API_BASE_URL}${API_PREFIX}/GetUserCompany`,
      {},
      {
        headers: {
          'Rediacc-UserEmail': email,
          'Rediacc-UserHash': passwordHash,
        },
      }
    )
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