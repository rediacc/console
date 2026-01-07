import {
  extractNextToken,
  parsePrivilegeAuthenticationRequest,
  parseLoginResult,
} from '@rediacc/shared/api';
import { isEncrypted } from '@rediacc/shared/encryption';
import { typedApi, apiClient } from './api.js';
import { contextService } from './context.js';
import { nodeCryptoProvider } from '../adapters/crypto.js';
import { t } from '../i18n/index.js';
import { EXIT_CODES } from '../types/index.js';
import { askPassword } from '../utils/prompt.js';

class AuthService {
  private cachedMasterPassword: string | null = null;

  /**
   * Login to the API and save credentials to a context.
   * If contextName is provided, creates/updates that context.
   * Otherwise, uses the current context.
   */
  async login(
    email: string,
    password: string,
    options: { sessionName?: string; contextName?: string; apiUrl?: string } = {}
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
    const authResult = parseLoginResult(response);
    if (!authResult.isAuthorized) {
      return {
        success: false,
        message: response.message || 'Authentication failed',
      };
    }

    // Extract token from login response
    // Note: Token rotation in apiClient.login() can't save the token because no context exists yet.
    // We must extract it here and pass it to saveLoginCredentials.
    const token = extractNextToken(response);

    if (!token) {
      return {
        success: false,
        message: 'Login succeeded but no request token was returned from server',
      };
    }

    // Determine the context name to use
    const contextName = options.contextName ?? (await contextService.getCurrentName()) ?? 'default';
    const apiUrl = options.apiUrl ?? (await apiClient.getApiUrl());

    // Prepare credentials to save
    const credentials: {
      apiUrl: string;
      token: string;
      userEmail: string;
      masterPassword?: string;
    } = {
      apiUrl,
      token,
      userEmail: email,
    };

    // Only store master password if organization has encryption enabled
    if (isEncrypted(authResult.vaultOrganization)) {
      const encryptedPassword = await nodeCryptoProvider.encrypt(password, password);
      credentials.masterPassword = encryptedPassword;
      this.cachedMasterPassword = password;
    } else {
      this.cachedMasterPassword = null;
    }

    // Save credentials to context
    await contextService.saveLoginCredentials(contextName, credentials);

    return { success: true };
  }

  async privilegeWithTFA(tfaCode: string): Promise<{ success: boolean; message?: string }> {
    const response = await typedApi.PrivilegeAuthenticationRequest({ tFACode: tfaCode });
    const result = parsePrivilegeAuthenticationRequest(response as never);

    if (!result.isAuthorized) {
      return {
        success: false,
        message: result.result ?? 'TFA verification failed',
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

    // Clear credentials from current context
    await contextService.clearCredentials();
    this.cachedMasterPassword = null;
  }

  async isAuthenticated(): Promise<boolean> {
    return contextService.hasToken();
  }

  async getStoredEmail(): Promise<string | null> {
    return contextService.getUserEmail();
  }

  async getMasterPassword(inputPassword?: string): Promise<string | null> {
    const encrypted = await contextService.getMasterPassword();
    if (!encrypted) return null;

    if (!inputPassword) {
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
    await contextService.setMasterPassword(encrypted);
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
    const encrypted = await contextService.getMasterPassword();

    if (encrypted) {
      // In non-interactive mode (no TTY), skip prompting and throw error
      if (!process.stdin.isTTY) {
        throw new AuthError(
          'Master password required but running in non-interactive mode. Set REDIACC_MASTER_PASSWORD environment variable.',
          EXIT_CODES.AUTH_REQUIRED
        );
      }

      // Prompt user for password
      const password = await askPassword(t('prompts.masterPassword'));

      try {
        const decrypted = await nodeCryptoProvider.decrypt(encrypted, password);
        this.cachedMasterPassword = decrypted;
        return decrypted;
      } catch {
        throw new AuthError('Invalid master password', EXIT_CODES.AUTH_REQUIRED);
      }
    }

    // No stored password - organization doesn't have encryption enabled
    throw new AuthError(
      'No master password configured. Organization may not have encryption enabled.',
      EXIT_CODES.AUTH_REQUIRED
    );
  }

  clearCachedPassword(): void {
    this.cachedMasterPassword = null;
  }

  async requireAuth(): Promise<void> {
    const isAuth = await this.isAuthenticated();
    if (!isAuth) {
      throw new AuthError('Not authenticated. Please run: rdc login', EXIT_CODES.AUTH_REQUIRED);
    }
  }

  async register(
    organizationName: string,
    email: string,
    password: string
  ): Promise<{ success: boolean; message?: string }> {
    const passwordHash = await nodeCryptoProvider.generateHash(password);

    try {
      await apiClient.register(organizationName, email, passwordHash);
      return { success: true };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Registration failed';
      return { success: false, message };
    }
  }

  async activate(
    email: string,
    password: string,
    code: string
  ): Promise<{ success: boolean; message?: string }> {
    const passwordHash = await nodeCryptoProvider.generateHash(password);

    try {
      await apiClient.activateUser(email, code, passwordHash);
      return { success: true };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Activation failed';
      return { success: false, message };
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
