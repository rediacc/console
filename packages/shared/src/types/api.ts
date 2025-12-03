export interface ApiResultSet<T> {
  data: T[]
  resultSetIndex?: number
  resultSetName?: string
}

export interface ApiResponse<T = unknown> {
  failure: number
  errors: string[]
  message: string
  resultSets: Array<ApiResultSet<T>>
  status?: number
  isTFAEnabled?: boolean
  isAuthorized?: boolean
  authenticationStatus?: string
  nextRequestToken?: string
}

export interface ApiErrorDetail {
  status?: number
  code?: string
  details?: unknown
  meta?: Record<string, unknown>
}

export class ApiError extends Error {
  status?: number
  code?: string
  details?: unknown
  meta?: Record<string, unknown>

  constructor(message: string, info?: ApiErrorDetail) {
    super(message)
    this.name = 'ApiError'
    if (info) {
      this.status = info.status
      this.code = info.code
      this.details = info.details
      this.meta = info.meta
    }
  }
}
