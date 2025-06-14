/**
 * Secure Token Service
 * 
 * This service manages authentication tokens in memory only, preventing exposure
 * through Redux DevTools or other state inspection tools.
 * 
 * Security features:
 * - Tokens stored in encrypted memory (using secureMemoryStorage)
 * - No token exposure in Redux state
 * - Automatic cleanup on logout
 * - Token rotation support
 */

import { secureStorage } from '@/utils/secureMemoryStorage'

class TokenService {
  private static instance: TokenService
  private readonly TOKEN_KEY = 'auth_token'

  private constructor() {
    // Private constructor for singleton pattern
  }

  static getInstance(): TokenService {
    if (!TokenService.instance) {
      TokenService.instance = new TokenService()
    }
    return TokenService.instance
  }

  /**
   * Store token securely in encrypted memory
   */
  async setToken(token: string): Promise<void> {
    if (!token) {
      throw new Error('Token cannot be empty')
    }
    await secureStorage.setItem(this.TOKEN_KEY, token)
  }

  /**
   * Retrieve token from secure storage
   */
  async getToken(): Promise<string | null> {
    return await secureStorage.getItem(this.TOKEN_KEY)
  }

  /**
   * Update token (for rotation)
   */
  updateToken = (newToken: string): Promise<void> => this.setToken(newToken)

  /**
   * Clear token from memory
   */
  clearToken(): void {
    secureStorage.removeItem(this.TOKEN_KEY)
  }

  /**
   * Check if token exists
   */
  hasToken(): boolean {
    return secureStorage.hasItem(this.TOKEN_KEY)
  }

  /**
   * Secure wipe of all auth data
   */
  secureWipe = (): void => this.clearToken()
}

// Export singleton instance
export const tokenService = TokenService.getInstance()

// Helper functions for backward compatibility
export const getAuthToken = (): Promise<string | null> => tokenService.getToken()
export const setAuthToken = (token: string): Promise<void> => tokenService.setToken(token)
export const clearAuthToken = (): void => tokenService.clearToken()