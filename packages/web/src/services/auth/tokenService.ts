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
 * - Token rotation support with versioning and mutex locking
 * - Race condition prevention through TokenLockManager
 */

import { secureMemoryStorage as secureStorage } from '@/services/crypto';
import { tokenLockManager } from './tokenLockManager';

interface TokenMetadata {
  token: string;
  version: number;
  timestamp: number;
}

class TokenService {
  private readonly TOKEN_KEY = 'auth_token';

  constructor() {
    // Intentionally public for simple singleton export below
  }

  /**
   * Store token securely in encrypted memory with versioning
   * Uses lock to prevent race conditions
   */
  async setToken(token: string): Promise<void> {
    if (!token) {
      throw new Error('Token cannot be empty');
    }

    return tokenLockManager.withLock(async () => {
      const version = tokenLockManager.nextVersion();
      const metadata: TokenMetadata = {
        token,
        version,
        timestamp: Date.now(),
      };

      await secureStorage.setItem(this.TOKEN_KEY, JSON.stringify(metadata));
    });
  }

  /**
   * Retrieve token from secure storage
   * Uses lock to ensure consistency with concurrent writes
   */
  async getToken(): Promise<string | null> {
    return tokenLockManager.withLock(async () => {
      const data = await secureStorage.getItem(this.TOKEN_KEY);
      if (!data) return null;

      try {
        const metadata: TokenMetadata = JSON.parse(data);

        // Validate version to detect stale overwrites
        if (!tokenLockManager.isVersionCurrent(metadata.version)) {
          console.warn('[TokenService] Token version mismatch - possible race condition detected', {
            tokenVersion: metadata.version,
            currentVersion: tokenLockManager.getCurrentVersion(),
          });
          return null;
        }

        return metadata.token;
      } catch (error) {
        console.error('[TokenService] Failed to parse token metadata:', error);
        return null;
      }
    });
  }

  /**
   * Update token (for rotation)
   * Uses lock to prevent concurrent updates
   */
  updateToken = (newToken: string): Promise<void> => this.setToken(newToken);

  /**
   * Clear token from memory
   * Uses lock to prevent race with concurrent reads/writes
   */
  async clearToken(): Promise<void> {
    return tokenLockManager.withLock(async () => {
      await Promise.resolve();
      secureStorage.removeItem(this.TOKEN_KEY);
    });
  }

  /**
   * Check if token exists
   * Simple check without locking (non-critical operation)
   */
  hasToken(): boolean {
    return secureStorage.hasItem(this.TOKEN_KEY);
  }

  /**
   * Secure wipe of all auth data
   * Uses lock to ensure clean state
   */
  async secureWipe(): Promise<void> {
    await this.clearToken();
    // Also clear fork tokens when logging out
    this.clearForkTokens();
  }

  /**
   * Clear fork tokens on logout
   */
  private clearForkTokens(): void {
    try {
      // Import dynamically to avoid circular dependencies
      void import('./forkTokenService').then(({ forkTokenService }) => {
        forkTokenService.clearAllForkTokens();
      });
    } catch {
      // Silently fail - fork token cleanup is not critical for logout
    }
  }
}

// Export singleton instance
export const tokenService = new TokenService();
