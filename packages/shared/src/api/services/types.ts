import type { ApiResponse } from '../../types/api'

export interface ApiClient {
  get<T = unknown>(endpoint: string, params?: Record<string, unknown>, config?: Record<string, unknown>): Promise<ApiResponse<T>>
  post<T = unknown>(endpoint: string, data?: Record<string, unknown>, config?: Record<string, unknown>): Promise<ApiResponse<T>>
  put<T = unknown>(endpoint: string, data?: Record<string, unknown>, config?: Record<string, unknown>): Promise<ApiResponse<T>>
  delete<T = unknown>(endpoint: string, data?: Record<string, unknown>, config?: Record<string, unknown>): Promise<ApiResponse<T>>
}

export type ApiRequestConfig = Record<string, unknown>
