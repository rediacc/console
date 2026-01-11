/**
 * Fork Token Service
 *
 * Manages fork authentication tokens for secure rediacc:// protocol operations.
 * Fork tokens are isolated from the main session and have limited lifespans.
 */

import { typedApi } from '@/api/client';
import { secureMemoryStorage as secureStorage } from '@/services/crypto';
import { parseForkAuthenticationRequest } from '@rediacc/shared/api';

interface ForkTokenInfo {
  token: string;
  expiresAt: number;
  parentRequestId: number | null;
  name: string;
}

// Helper to check if token is expired
const isTokenExpired = (expiresAt: number): boolean => Date.now() >= expiresAt;

// Helper to parse fork token info from storage
const parseForkTokenInfo = (data: string): ForkTokenInfo | null => {
  try {
    return JSON.parse(data) as ForkTokenInfo;
  } catch {
    return null;
  }
};

// Helper to get storage key for action
const getStorageKey = (prefix: string, action: string): string => `${prefix}${action}`;

class ForkTokenService {
  private readonly FORK_TOKEN_PREFIX = 'fork_token_';
  private readonly DEFAULT_EXPIRATION_HOURS = 2;

  constructor() {
    // Intentionally public for simple singleton export below
  }

  /**
   * Create a new fork token for rediacc:// protocol usage
   */
  async createForkToken(
    action: string,
    expirationHours: number = this.DEFAULT_EXPIRATION_HOURS
  ): Promise<string> {
    const childName = `desktop-${action}-${Date.now()}`;

    try {
      const credentials = await this.callForkAuthenticationRequest(childName, expirationHours);
      const forkToken = credentials.nextRequestToken;
      const parentRequestId = credentials.parentRequestId;

      if (!forkToken) {
        throw new Error('Failed to create fork token: No token returned');
      }

      const forkTokenInfo: ForkTokenInfo = {
        token: forkToken,
        expiresAt: Date.now() + expirationHours * 60 * 60 * 1000,
        parentRequestId,
        name: childName,
      };

      const storageKey = getStorageKey(this.FORK_TOKEN_PREFIX, action);
      await secureStorage.setItem(storageKey, JSON.stringify(forkTokenInfo));

      return forkToken;
    } catch (error) {
      console.error('Failed to create fork token:', error);
      throw new Error(
        `Failed to create fork token: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
    }
  }

  /**
   * Get existing fork token for an action (if valid)
   */
  async getForkToken(action: string): Promise<string | null> {
    const storageKey = getStorageKey(this.FORK_TOKEN_PREFIX, action);
    const forkTokenInfoStr = await secureStorage.getItem(storageKey);

    if (!forkTokenInfoStr) return null;

    const forkTokenInfo = parseForkTokenInfo(forkTokenInfoStr);
    if (!forkTokenInfo) {
      secureStorage.removeItem(storageKey);
      return null;
    }

    if (isTokenExpired(forkTokenInfo.expiresAt)) {
      secureStorage.removeItem(storageKey);
      return null;
    }

    return forkTokenInfo.token;
  }

  /**
   * Get or create fork token for an action
   */
  async getOrCreateForkToken(
    action: string,
    expirationHours: number = this.DEFAULT_EXPIRATION_HOURS
  ): Promise<string> {
    const existingToken = await this.getForkToken(action);
    if (existingToken) return existingToken;

    return await this.createForkToken(action, expirationHours);
  }

  /**
   * Create a fresh fork token for an action, clearing any existing token
   * This ensures each call gets a new token for security and proper rotation
   */
  async createFreshForkToken(
    action: string,
    expirationHours: number = this.DEFAULT_EXPIRATION_HOURS
  ): Promise<string> {
    const storageKey = getStorageKey(this.FORK_TOKEN_PREFIX, action);
    const existingTokenInfoStr = await secureStorage.getItem(storageKey);

    if (existingTokenInfoStr) {
      // Attempt to parse (ignoring errors for corrupted data)
      parseForkTokenInfo(existingTokenInfoStr);
      secureStorage.removeItem(storageKey);
    }

    return await this.createForkToken(action, expirationHours);
  }

  /**
   * Clear all fork tokens
   */
  clearAllForkTokens(): void {
    const keys = secureStorage.keys();
    keys
      .filter((key) => key.startsWith(this.FORK_TOKEN_PREFIX))
      .forEach((key) => secureStorage.removeItem(key));
  }

  /**
   * Clear expired fork tokens
   */
  async clearExpiredForkTokens(): Promise<void> {
    const keys = secureStorage.keys();
    const forkTokenKeys = keys.filter((key) => key.startsWith(this.FORK_TOKEN_PREFIX));

    for (const key of forkTokenKeys) {
      await this.clearTokenIfExpired(key);
    }
  }

  /**
   * Check and clear a single token if expired
   */
  private async clearTokenIfExpired(key: string): Promise<void> {
    const forkTokenInfoStr = await secureStorage.getItem(key);
    if (!forkTokenInfoStr) return;

    const forkTokenInfo = parseForkTokenInfo(forkTokenInfoStr);
    if (!forkTokenInfo || isTokenExpired(forkTokenInfo.expiresAt)) {
      secureStorage.removeItem(key);
    }
  }

  /**
   * Call the ForkAuthenticationRequest API
   */
  private async callForkAuthenticationRequest(childName: string, expirationHours: number) {
    const response = await typedApi.ForkAuthenticationRequest({
      childName,
      tokenExpirationHours: expirationHours,
    });
    const credentials = parseForkAuthenticationRequest(response as never);

    if (!credentials.nextRequestToken) {
      throw new Error('Fork token data not found in API response');
    }

    return credentials;
  }
}

// Export singleton instance
export const forkTokenService = new ForkTokenService();

// Helper function (only createFreshForkToken is used externally)
export const createFreshForkToken = (action: string, expirationHours?: number): Promise<string> =>
  forkTokenService.createFreshForkToken(action, expirationHours);
