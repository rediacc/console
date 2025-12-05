/**
 * Service for secure master password management
 * Stores master password in secure memory storage instead of Redux state
 */

import { secureStorage } from '../utils/secureMemoryStorage';

const MASTER_PASSWORD_KEY = 'z^X8zFgx%SqhMAsK';

class MasterPasswordService {
  /**
   * Store master password in secure memory
   */
  async setMasterPassword(password: string | null): Promise<void> {
    if (password) {
      await secureStorage.setItem(MASTER_PASSWORD_KEY, password);
    } else {
      secureStorage.removeItem(MASTER_PASSWORD_KEY);
    }
  }

  /**
   * Retrieve master password from secure memory
   */
  async getMasterPassword(): Promise<string | null> {
    return await secureStorage.getItem(MASTER_PASSWORD_KEY);
  }

  /**
   * Check if master password exists
   */
  hasMasterPassword(): boolean {
    return secureStorage.hasItem(MASTER_PASSWORD_KEY);
  }

  /**
   * Clear master password from memory
   */
  clearMasterPassword(): void {
    secureStorage.removeItem(MASTER_PASSWORD_KEY);
  }
}

// Export singleton instance
export const masterPasswordService = new MasterPasswordService();
