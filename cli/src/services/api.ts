import axios, { AxiosInstance, AxiosRequestConfig } from 'axios'
import { nodeStorageAdapter } from '../adapters/storage.js'
import { nodeCryptoProvider } from '../adapters/crypto.js'
import { EXIT_CODES } from '../types/index.js'

const API_PREFIX = '/StoredProcedure'
const STORAGE_KEYS = {
  TOKEN: 'token',
  API_URL: 'apiUrl',
  MASTER_PASSWORD: 'masterPassword',
} as const

// Vault encryption utilities
function isVaultField(key: string): boolean {
  return key.toLowerCase().includes('vault')
}

function hasVaultFields(data: unknown): boolean {
  if (!data) return false
  if (Array.isArray(data)) {
    return data.some((item) => hasVaultFields(item))
  }
  if (typeof data === 'object') {
    return Object.keys(data as Record<string, unknown>).some((key) => {
      if (isVaultField(key)) return true
      const nested = (data as Record<string, unknown>)[key]
      return hasVaultFields(nested)
    })
  }
  return false
}

function isBase64Encrypted(value: string): boolean {
  return /^[A-Za-z0-9+/]+=*$/.test(value)
}

async function transformVaultFields<T>(
  value: T,
  transformer: (input: string) => Promise<string>
): Promise<T> {
  if (Array.isArray(value)) {
    const result = await Promise.all(
      value.map((item) => transformVaultFields(item, transformer))
    )
    return result as T
  }

  if (typeof value === 'object' && value !== null) {
    const target: Record<string, unknown> = {}
    const entries = Object.entries(value as Record<string, unknown>)
    await Promise.all(
      entries.map(async ([key, entryValue]) => {
        if (isVaultField(key) && typeof entryValue === 'string' && entryValue.length > 0) {
          target[key] = await transformer(entryValue)
        } else if (Array.isArray(entryValue) || (entryValue && typeof entryValue === 'object')) {
          target[key] = await transformVaultFields(entryValue, transformer)
        } else {
          target[key] = entryValue
        }
      })
    )
    return target as T
  }

  return value
}

async function encryptRequestData<T>(data: T, password: string): Promise<T> {
  if (!password || !data) return data
  return transformVaultFields(data, (input) => nodeCryptoProvider.encrypt(input, password))
}

async function decryptResponseData<T>(data: T, password: string): Promise<T> {
  if (!password || !data) return data
  return transformVaultFields(data, async (input) => {
    if (!isBase64Encrypted(input)) return input
    try {
      return await nodeCryptoProvider.decrypt(input, password)
    } catch {
      return input
    }
  })
}

export interface ApiResponse<T = unknown> {
  failure: number
  errors: string[]
  message: string
  resultSets: Array<{
    data: T[]
    resultSetIndex?: number
  }>
  status?: number
  isTFAEnabled?: boolean
  isAuthorized?: boolean
  authenticationStatus?: string
}

class CliApiClient {
  private client: AxiosInstance
  private apiUrl: string = ''
  private initialized = false
  private masterPasswordGetter: (() => Promise<string>) | null = null

  constructor() {
    this.client = axios.create({
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })
  }

  setMasterPasswordGetter(getter: () => Promise<string>): void {
    this.masterPasswordGetter = getter
  }

  private async getMasterPassword(): Promise<string | null> {
    if (this.masterPasswordGetter) {
      try {
        return await this.masterPasswordGetter()
      } catch {
        return null
      }
    }
    return null
  }

  async initialize(): Promise<void> {
    if (this.initialized) return

    // Load API URL from storage or use default
    const storedUrl = await nodeStorageAdapter.getItem(STORAGE_KEYS.API_URL)
    this.apiUrl = storedUrl || process.env.REDIACC_API_URL || 'https://www.rediacc.com/api'
    this.client.defaults.baseURL = `${this.apiUrl}${API_PREFIX}`
    this.initialized = true
  }

  async setApiUrl(url: string): Promise<void> {
    this.apiUrl = url
    this.client.defaults.baseURL = `${url}${API_PREFIX}`
    await nodeStorageAdapter.setItem(STORAGE_KEYS.API_URL, url)
  }

  getApiUrl(): string {
    return this.apiUrl
  }

  async login(
    email: string,
    passwordHash: string,
    sessionName = 'CLI Session'
  ): Promise<ApiResponse> {
    await this.initialize()

    const response = await this.client.post<ApiResponse>(
      '/CreateAuthenticationRequest',
      { name: sessionName },
      {
        headers: {
          'Rediacc-UserEmail': email,
          'Rediacc-UserHash': passwordHash,
        },
      }
    )

    const data = response.data
    await this.handleTokenRotation(data)
    return data
  }

  async logout(): Promise<ApiResponse> {
    return this.post('/DeleteUserRequest', {})
  }

  async activateUser(
    email: string,
    activationCode: string,
    passwordHash: string
  ): Promise<ApiResponse> {
    await this.initialize()

    const response = await this.client.post<ApiResponse>(
      '/ActivateUserAccount',
      { activationCode },
      {
        headers: {
          'Rediacc-UserEmail': email,
          'Rediacc-UserHash': passwordHash,
        },
      }
    )

    return response.data
  }

  async get<T = unknown>(
    endpoint: string,
    params?: Record<string, unknown>,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    return this.makeRequest<T>(endpoint, params, config)
  }

  async post<T = unknown>(
    endpoint: string,
    data: Record<string, unknown>,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    return this.makeRequest<T>(endpoint, data, config)
  }

  private async makeRequest<T>(
    endpoint: string,
    data?: Record<string, unknown>,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    await this.initialize()

    const token = await this.getToken()
    const headers: Record<string, string> = {}

    // Copy string headers from config
    if (config?.headers) {
      for (const [key, value] of Object.entries(config.headers)) {
        if (typeof value === 'string') {
          headers[key] = value
        }
      }
    }

    if (token) {
      headers['Rediacc-RequestToken'] = token
    }

    try {
      // Encrypt vault fields in request data if present
      let requestData = data || {}
      const masterPassword = await this.getMasterPassword()

      if (masterPassword && hasVaultFields(requestData)) {
        requestData = await encryptRequestData(requestData, masterPassword)
      }

      const response = await this.client.post<ApiResponse<T>>(
        endpoint,
        requestData,
        { ...config, headers }
      )

      let responseData = response.data
      await this.handleTokenRotation(responseData)

      if (responseData.failure !== 0) {
        throw this.createApiError(responseData)
      }

      // Decrypt vault fields in response data
      if (masterPassword && hasVaultFields(responseData)) {
        responseData = await decryptResponseData(responseData, masterPassword)
      }

      return responseData
    } catch (error) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 401) {
          throw new CliApiError('Authentication required', EXIT_CODES.AUTH_REQUIRED)
        }
        if (error.response?.status === 403) {
          throw new CliApiError('Permission denied', EXIT_CODES.PERMISSION_DENIED)
        }
        if (error.response?.status === 404) {
          throw new CliApiError('Resource not found', EXIT_CODES.NOT_FOUND)
        }
        if (!error.response) {
          throw new CliApiError('Network error: ' + error.message, EXIT_CODES.NETWORK_ERROR)
        }
      }
      throw error
    }
  }

  private async handleTokenRotation(response: ApiResponse): Promise<void> {
    const firstRow = response.resultSets?.[0]?.data?.[0] as Record<string, unknown> | undefined
    const newToken = firstRow?.nextRequestToken as string | undefined
    if (newToken) {
      await nodeStorageAdapter.setItem(STORAGE_KEYS.TOKEN, newToken)
    }
  }

  private async getToken(): Promise<string | null> {
    // Check environment variable first
    const envToken = process.env.REDIACC_TOKEN
    if (envToken) return envToken

    return nodeStorageAdapter.getItem(STORAGE_KEYS.TOKEN)
  }

  async setToken(token: string): Promise<void> {
    await nodeStorageAdapter.setItem(STORAGE_KEYS.TOKEN, token)
  }

  async clearToken(): Promise<void> {
    await nodeStorageAdapter.removeItem(STORAGE_KEYS.TOKEN)
  }

  async hasToken(): Promise<boolean> {
    const token = await this.getToken()
    return token !== null
  }

  private createApiError(response: ApiResponse): CliApiError {
    const message = response.errors?.join('; ') || response.message || 'API request failed'
    return new CliApiError(message, EXIT_CODES.GENERAL_ERROR, response)
  }
}

export class CliApiError extends Error {
  constructor(
    message: string,
    public readonly exitCode: number = EXIT_CODES.GENERAL_ERROR,
    public readonly response?: ApiResponse
  ) {
    super(message)
    this.name = 'CliApiError'
  }
}

export const apiClient = new CliApiClient()
export default apiClient
