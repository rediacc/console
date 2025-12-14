import { parseAuthenticationResult } from '@rediacc/shared/api/services/auth';
import { isEncrypted } from '@rediacc/shared/encryption';
import type { ApiResponse } from '@rediacc/shared/types';
import { api, apiClient } from './api.js';
import { nodeCryptoProvider } from '../adapters/crypto.js';
import { nodeStorageAdapter } from '../adapters/storage.js';
import { EXIT_CODES } from '../types/index.js';
import { askPassword } from '../utils/prompt.js';

const STORAGE_KEYS = {
  TOKEN: 'token',
  MASTER_PASSWORD: 'masterPassword',
  USER_EMAIL: 'userEmail',
} as const;

class AuthService {
  private cachedMasterPassword: string | null = null;
  async login(
    email: string,
    password: string,
    options: { sessionName?: string } = {}
  ): Promise<{ success: boolean; isTFAEnabled?: boolean; message?: string }> {
    // Hash the password
    const passwordHash = await nodeCryptoProvider.generateHash(password);

    // Call API
    const response = await apiClient.login(email, passwordHash, options.sessionName);

    // Check for 2FA requirement
    if (response.isTFAEnabled) {
      return {
        success: false,
        isTFAEnabled: true,
        message: 'Two-factor authentication required',
      };
    }

    // Check authentication status
    const authResult = parseAuthenticationResult(response as ApiResponse);
    if (!authResult.isAuthorized) {
      return {
        success: false,
        message: response.message || 'Authentication failed',
      };
    }

    // Store email for convenience
    await nodeStorageAdapter.setItem(STORAGE_KEYS.USER_EMAIL, email);

    // Only store master password if company has encryption enabled
    // This matches the console's behavior - see web/src/pages/login/index.tsx
    if (isEncrypted(authResult.vaultCompany)) {
      await this.setMasterPassword(password);
    } else {
      // Clear any previously stored password if company doesn't have encryption
      await nodeStorageAdapter.removeItem(STORAGE_KEYS.MASTER_PASSWORD);
      this.cachedMasterPassword = null;
    }

    return { success: true };
  }

  async privilegeWithTFA(tfaCode: string): Promise<{ success: boolean; message?: string }> {
    const result = await api.auth.verifyTfa(tfaCode);

    if (!result.isAuthorized) {
      return {
        success: false,
        message: result.result || 'TFA verification failed',
      };
    }

    return { success: true };
  }

  async logout(): Promise<void> {
    try {
      // Call API to invalidate token
      await apiClient.logout();
    } catch {
      // Ignore errors during logout
    }

    // Clear local credentials
    await apiClient.clearToken();
    await nodeStorageAdapter.removeItem(STORAGE_KEYS.MASTER_PASSWORD);
    await nodeStorageAdapter.removeItem(STORAGE_KEYS.USER_EMAIL);
  }

  async isAuthenticated(): Promise<boolean> {
    return apiClient.hasToken();
  }

  async getStoredEmail(): Promise<string | null> {
    return nodeStorageAdapter.getItem(STORAGE_KEYS.USER_EMAIL);
  }

  async getMasterPassword(inputPassword?: string): Promise<string | null> {
    const encrypted = await nodeStorageAdapter.getItem(STORAGE_KEYS.MASTER_PASSWORD);
    if (!encrypted) return null;

    if (!inputPassword) {
      // Can't decrypt without the password
      return null;
    }

    try {
      return await nodeCryptoProvider.decrypt(encrypted, inputPassword);
    } catch {
      return null;
    }
  }

  async setMasterPassword(password: string): Promise<void> {
    const encrypted = await nodeCryptoProvider.encrypt(password, password);
    await nodeStorageAdapter.setItem(STORAGE_KEYS.MASTER_PASSWORD, encrypted);
    this.cachedMasterPassword = password;
  }

  async requireMasterPassword(): Promise<string> {
    // Return cached password if available
    if (this.cachedMasterPassword) {
      return this.cachedMasterPassword;
    }

    // Check for environment variable (for non-interactive/scripted usage)
    const envPassword = process.env.REDIACC_MASTER_PASSWORD;
    if (envPassword) {
      this.cachedMasterPassword = envPassword;
      return envPassword;
    }

    // Try to get stored encrypted password
    const encrypted = await nodeStorageAdapter.getItem(STORAGE_KEYS.MASTER_PASSWORD);

    if (encrypted) {
      // We need the password to decrypt it - prompt user
      const password = await askPassword('Enter your master password:');

      try {
        const decrypted = await nodeCryptoProvider.decrypt(encrypted, password);
        // Verify the decrypted password matches by encrypting it again
        // If it decrypts successfully, we have the right password
        this.cachedMasterPassword = decrypted;
        return decrypted;
      } catch {
        // Decryption failed - wrong password
        throw new AuthError('Invalid master password', EXIT_CODES.AUTH_REQUIRED);
      }
    }

    // No stored password - company doesn't have encryption enabled
    // Don't prompt for new password; vault operations will skip client-side encryption
    throw new AuthError(
      'No master password configured. Company may not have encryption enabled.',
      EXIT_CODES.AUTH_REQUIRED
    );
  }

  clearCachedPassword(): void {
    this.cachedMasterPassword = null;
  }

  async requireAuth(): Promise<void> {
    const isAuth = await this.isAuthenticated();
    if (!isAuth) {
      throw new AuthError('Not authenticated. Please run: rediacc login', EXIT_CODES.AUTH_REQUIRED);
    }
  }
}

export class AuthError extends Error {
  constructor(
    message: string,
    public readonly exitCode: number = EXIT_CODES.AUTH_REQUIRED
  ) {
    super(message);
    this.name = 'AuthError';
  }
}

export const authService = new AuthService();
