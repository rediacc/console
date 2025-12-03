// Proper types for API response data

export interface AuthResponse {
  nextRequestToken?: string
  authenticationStatus?: string
  isTFAEnabled?: boolean
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
