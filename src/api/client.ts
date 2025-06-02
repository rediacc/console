import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { store } from '@/store/store'
import { updateToken, logout } from '@/store/auth/authSlice'
import toast from 'react-hot-toast'

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
      (response) => {
        const data = response.data as ApiResponse

        // Check for API-level failure
        if (data.failure !== 0) {
          const errorMessage = data.errors?.join('; ') || data.message || 'Request failed'
          toast.error(errorMessage)
          return Promise.reject(new Error(errorMessage))
        }

        // Handle token rotation
        if (data.tables?.[0]?.data?.[0]?.nextRequestCredential) {
          const newToken = data.tables[0].data[0].nextRequestCredential
          store.dispatch(updateToken(newToken))
        }

        return response
      },
      (error) => {
        if (error.response?.status === 401) {
          store.dispatch(logout())
          toast.error('Session expired. Please login again.')
          window.location.href = `${import.meta.env.BASE_URL}login`
        } else if (error.response?.status >= 500) {
          toast.error('Server error. Please try again later.')
        } else if (error.request) {
          toast.error('Network error. Please check your connection.')
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

  // Generic API methods
  async get<T = any>(endpoint: string, params?: any): Promise<ApiResponse<T>> {
    const response = await this.client.post<ApiResponse<T>>(endpoint, params || {})
    return response.data
  }

  async post<T = any>(endpoint: string, data: any): Promise<ApiResponse<T>> {
    const response = await this.client.post<ApiResponse<T>>(endpoint, data)
    return response.data
  }

  async put<T = any>(endpoint: string, data: any): Promise<ApiResponse<T>> {
    const response = await this.client.post<ApiResponse<T>>(endpoint, data)
    return response.data
  }

  async delete<T = any>(endpoint: string, data: any): Promise<ApiResponse<T>> {
    const response = await this.client.post<ApiResponse<T>>(endpoint, data)
    return response.data
  }
}

export const apiClient = new ApiClient()
export default apiClient