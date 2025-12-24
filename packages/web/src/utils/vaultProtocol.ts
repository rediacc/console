import { cryptoService } from '@/services/crypto';
import {
  isEncrypted,
  VaultProtocolState,
  analyzeVaultProtocolState,
} from '@rediacc/shared/encryption';

// Re-export shared utilities for backward compatibility
export { isEncrypted, VaultProtocolState, analyzeVaultProtocolState };

/**
 * Validate master password by attempting to decrypt VaultCompany
 * @param encryptedVaultCompany The encrypted VaultCompany value
 * @param masterPassword The master password to validate
 * @returns true if password is valid, false otherwise
 */
export async function validateMasterPassword(
  encryptedVaultCompany: string,
  masterPassword: string
): Promise<boolean> {
  try {
    // Try to decrypt the vault content
    const decrypted = await cryptoService.decryptString(encryptedVaultCompany, masterPassword);

    // If decryption succeeds, the password is valid
    // The decrypted content should be valid JSON (even if it's just {})
    try {
      JSON.parse(decrypted);
      return true;
    } catch {
      // If it's not valid JSON after decryption, the password is wrong
      return false;
    }
  } catch {
    // Decryption failed - wrong password
    return false;
  }
}

/**
 * Create the encrypted sentinel value for VaultCompany
 * This is used to indicate that a company has enabled encryption
 * @param company The company name
 * @param masterPassword The master password to use for encryption
 * @returns The encrypted sentinel value
 */
export async function createVaultCompanySentinel(
  company: string,
  masterPassword: string
): Promise<string> {
  // Create a sentinel object with company name and timestamp
  const sentinel = {
    company,
    encryptionEnabled: true,
    timestamp: new Date().toISOString(),
  };

  // Encrypt the sentinel using the master password
  const encryptedSentinel = await cryptoService.encryptString(
    JSON.stringify(sentinel),
    masterPassword
  );
  return encryptedSentinel;
}

/**
 * Get user-friendly message for vault protocol state
 * Note: This returns message keys for i18n translation
 */
export function getVaultProtocolMessage(state: VaultProtocolState): {
  type: 'error' | 'warning' | 'info' | 'success';
  messageKey: string;
  message: string; // Fallback message
} {
  switch (state) {
    case VaultProtocolState.NOT_ENABLED:
      return {
        type: 'info',
        messageKey: 'auth:login.errors.companyNotEncrypted',
        message: 'Your company has not enabled vault encryption',
      };

    case VaultProtocolState.PASSWORD_REQUIRED:
      return {
        type: 'error',
        messageKey: 'auth:login.errors.masterPasswordRequired',
        message:
          'Your company requires a master password for vault encryption. Please enter the company master password.',
      };

    case VaultProtocolState.INVALID_PASSWORD:
      return {
        type: 'error',
        messageKey: 'auth:login.errors.invalidMasterPassword',
        message:
          'Invalid master password. Please check with your administrator for the correct company master password.',
      };

    case VaultProtocolState.VALID:
      return {
        type: 'success',
        messageKey: 'common:messages.success',
        message: 'Master password validated successfully',
      };

    case VaultProtocolState.PASSWORD_NOT_NEEDED:
      return {
        type: 'warning',
        messageKey: 'auth:login.errors.companyNotEncrypted',
        message:
          'Your company has not enabled vault encryption yet. The master password you entered will not be used.',
      };

    default:
      return {
        type: 'info',
        messageKey: '',
        message: '',
      };
  }
}
