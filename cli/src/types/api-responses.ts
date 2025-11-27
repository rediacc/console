// Proper types for API response data

export interface AuthResponse {
  nextRequestToken?: string
  authenticationStatus?: string
  isTFAEnabled?: boolean
}

export interface TokenForkResponse {
  requestToken?: string
}

export interface TFAResponse {
  isTFAEnabled?: boolean
  secret?: string
}

export interface QueueItemResponse {
  taskId?: string
  status?: string
  healthStatus?: string
  progress?: string
  consoleOutput?: string
  errorMessage?: string
  lastFailureReason?: string
  priority?: number
  retryCount?: number
  ageInMinutes?: number
  hasResponse?: boolean
  teamName?: string
  machineName?: string
  bridgeName?: string
  createdAt?: string
  updatedAt?: string
}

export interface UserResponse {
  activationCode?: string
  isRegistered?: boolean
}

export interface BridgeAuthResponse {
  authToken?: string
}

// Generic helper to extract first row with proper typing
export function getFirstRow<T>(
  resultSets: Array<{ data: unknown[]; resultSetIndex?: number }> | undefined,
  index = 0
): T | undefined {
  return resultSets?.[index]?.data?.[0] as T | undefined
}

// Helper to extract all rows
export function getAllRows<T>(
  resultSets: Array<{ data: unknown[]; resultSetIndex?: number }> | undefined,
  index = 0
): T[] {
  return (resultSets?.[index]?.data || []) as T[]
}
