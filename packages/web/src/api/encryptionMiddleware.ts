import { cryptoService } from '@/services/cryptoService';
import { masterPasswordService } from '@/services/masterPasswordService';
import { showMessage } from '@/utils/messages';

/**
 * Middleware to handle vault field encryption/decryption
 * Applied to axios request/response interceptors
 */

/**
 * Encrypts vault fields in request data before sending
 */
export async function encryptRequestData<T>(data: T): Promise<T> {
  const masterPassword = await masterPasswordService.getMasterPassword();

  if (!masterPassword || data === undefined || data === null) {
    return data;
  }

  try {
    return await cryptoService.encryptVaultFields(data, masterPassword);
  } catch (error) {
    showMessage('error', 'Failed to encrypt secure data');
    throw error;
  }
}

/**
 * Decrypts vault fields in response data after receiving
 */
export async function decryptResponseData<T>(data: T): Promise<T> {
  const masterPassword = await masterPasswordService.getMasterPassword();

  if (!masterPassword || data === undefined || data === null) {
    return data;
  }

  try {
    return await cryptoService.decryptVaultFields(data, masterPassword);
  } catch {
    showMessage('error', 'Failed to decrypt secure data - check your master password');
    // Return original data instead of throwing to allow app to continue
    return data;
  }
}

/**
 * Checks if any vault fields exist in the object
 */
export const hasVaultFields = (data: unknown): boolean => cryptoService.hasVaultFields(data);
