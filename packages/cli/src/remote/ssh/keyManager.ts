import { decodeSSHKey } from '../utils/sshKeyText.js';
import { createSecureTempFile, removeTempFile } from '../utils/tempFiles.js';

/**
 * Creates a temporary SSH key file with proper permissions
 *
 * @param sshKey - SSH private key content (plain text)
 * @returns Path to the temporary key file
 */
export function createTempSSHKeyFile(sshKey: string): Promise<string> {
  const normalizedKey = decodeSSHKey(sshKey);
  return createSecureTempFile(normalizedKey, {
    prefix: 'ssh-key',
    extension: '.pem',
  });
}

/**
 * Safely removes a temporary SSH key file
 *
 * @param keyFilePath - Path to the key file to remove
 */
export async function removeTempSSHKeyFile(keyFilePath: string): Promise<void> {
  await removeTempFile(keyFilePath);
}

/**
 * Validates an SSH key without decoding
 * Returns true if the key appears to be valid
 *
 * @param sshKey - SSH key to validate
 * @returns true if key appears valid
 */
export function isValidSSHKey(sshKey: string): boolean {
  try {
    decodeSSHKey(sshKey);
    return true;
  } catch {
    return false;
  }
}
