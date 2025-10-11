/**
 * Fork Token Service
 *
 * Manages fork authentication tokens for secure rediacc:// protocol operations.
 * Fork tokens are isolated from the main session and have limited lifespans.
 */

import { secureStorage } from '@/utils/secureMemoryStorage'

export interface ForkTokenInfo {
  token: string
  expiresAt: number
  parentRequestId: number
  name: string
}

class ForkTokenService {
  private static instance: ForkTokenService
  private readonly FORK_TOKEN_PREFIX = 'fork_token_'
  private readonly DEFAULT_EXPIRATION_HOURS = 2

  private constructor() {
    // Private constructor for singleton pattern
  }

  static getInstance(): ForkTokenService {
    if (!ForkTokenService.instance) {
      ForkTokenService.instance = new ForkTokenService()
    }
    return ForkTokenService.instance
  }

  /**
   * Create a new fork token for rediacc:// protocol usage
   */
  async createForkToken(action: string, expirationHours: number = this.DEFAULT_EXPIRATION_HOURS): Promise<string> {
    // Generate unique name for this fork token
    const childName = `desktop-${action}-${Date.now()}`

    try {
      // Call the API to create fork token (uses current session as parent)
      const response = await this.callForkAuthenticationRequest(childName, expirationHours)

      const forkToken = response.nextRequestToken
      const parentRequestId = response.parentRequestId

      if (!forkToken) {
        throw new Error('Failed to create fork token: No token returned')
      }

      // Store fork token info locally for tracking
      const forkTokenInfo: ForkTokenInfo = {
        token: forkToken,
        expiresAt: Date.now() + (expirationHours * 60 * 60 * 1000),
        parentRequestId,
        name: childName
      }

      const storageKey = `${this.FORK_TOKEN_PREFIX}${action}`
      await secureStorage.setItem(storageKey, JSON.stringify(forkTokenInfo))

      return forkToken
    } catch (error) {
      console.error('Failed to create fork token:', error)
      throw new Error(`Failed to create fork token: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }

  /**
   * Get existing fork token for an action (if valid)
   */
  async getForkToken(action: string): Promise<string | null> {
    const storageKey = `${this.FORK_TOKEN_PREFIX}${action}`
    const forkTokenInfoStr = await secureStorage.getItem(storageKey)

    if (!forkTokenInfoStr) {
      return null
    }

    try {
      const forkTokenInfo: ForkTokenInfo = JSON.parse(forkTokenInfoStr)

      // Check if token has expired
      if (Date.now() >= forkTokenInfo.expiresAt) {
        // Clean up expired token
        secureStorage.removeItem(storageKey)
        return null
      }

      return forkTokenInfo.token
    } catch (error) {
      // Clean up corrupted token data
      secureStorage.removeItem(storageKey)
      return null
    }
  }

  /**
   * Get or create fork token for an action
   */
  async getOrCreateForkToken(action: string, expirationHours: number = this.DEFAULT_EXPIRATION_HOURS): Promise<string> {
    // Try to get existing valid token first
    const existingToken = await this.getForkToken(action)
    if (existingToken) {
      return existingToken
    }

    // Create new fork token
    return await this.createForkToken(action, expirationHours)
  }

  /**
   * Create a fresh fork token for an action, clearing any existing token
   * This ensures each call gets a new token for security and proper rotation
   */
  async createFreshForkToken(action: string, expirationHours: number = this.DEFAULT_EXPIRATION_HOURS): Promise<string> {
    // Clear any existing token for this action first
    const storageKey = `${this.FORK_TOKEN_PREFIX}${action}`
    const existingTokenInfoStr = await secureStorage.getItem(storageKey)

    if (existingTokenInfoStr) {
      try {
        const existingTokenInfo: ForkTokenInfo = JSON.parse(existingTokenInfoStr)
        console.log(`Clearing existing fork token for action: ${action}, token: ${existingTokenInfo.token.substring(0, 8)}...`)
      } catch (error) {
        console.log(`Clearing corrupted fork token data for action: ${action}`)
      }

      // Remove the old token
      await secureStorage.removeItem(storageKey)
    }

    // Create new fork token
    const newToken = await this.createForkToken(action, expirationHours)
    console.log(`Created fresh fork token for action: ${action}, token: ${newToken.substring(0, 8)}...`)

    return newToken
  }

  /**
   * Clear all fork tokens
   */
  clearAllForkTokens(): void {
    const keys = secureStorage.keys()
    keys.forEach(key => {
      if (key.startsWith(this.FORK_TOKEN_PREFIX)) {
        secureStorage.removeItem(key)
      }
    })
  }

  /**
   * Clear expired fork tokens
   */
  async clearExpiredForkTokens(): Promise<void> {
    const keys = secureStorage.keys()
    const now = Date.now()

    for (const key of keys) {
      if (key.startsWith(this.FORK_TOKEN_PREFIX)) {
        try {
          const forkTokenInfoStr = await secureStorage.getItem(key)
          if (forkTokenInfoStr) {
            const forkTokenInfo: ForkTokenInfo = JSON.parse(forkTokenInfoStr)
            if (now >= forkTokenInfo.expiresAt) {
              secureStorage.removeItem(key)
            }
          }
        } catch (error) {
          // Remove corrupted entries
          secureStorage.removeItem(key)
        }
      }
    }
  }

  /**
   * Call the ForkAuthenticationRequest API
   */
  private async callForkAuthenticationRequest(
    childName: string,
    expirationHours: number
  ): Promise<any> {
    // Import dynamically to avoid circular dependency
    const { apiClient } = await import('@/api/client')

    const response = await apiClient.post('/ForkAuthenticationRequest', {
      childName,
      tokenExpirationHours: expirationHours
    })

    // Find the "Credentials" result set which contains the fork token data
    // The API client automatically skips token rotation for ForkAuthenticationRequest calls
    const credentialsResultSet = response.resultSets?.find(
      (rs: any) => rs.resultSetName === 'Credentials'
    )

    if (!credentialsResultSet?.data?.[0]) {
      throw new Error('Fork token data not found in API response')
    }

    return credentialsResultSet.data[0]
  }
}

// Export singleton instance
export const forkTokenService = ForkTokenService.getInstance()

// Helper functions
export const createForkToken = (action: string, expirationHours?: number): Promise<string> =>
  forkTokenService.createForkToken(action, expirationHours)

export const getForkToken = (action: string): Promise<string | null> =>
  forkTokenService.getForkToken(action)

export const getOrCreateForkToken = (action: string, expirationHours?: number): Promise<string> =>
  forkTokenService.getOrCreateForkToken(action, expirationHours)

export const createFreshForkToken = (action: string, expirationHours?: number): Promise<string> =>
  forkTokenService.createFreshForkToken(action, expirationHours)

export const clearAllForkTokens = (): void =>
  forkTokenService.clearAllForkTokens()