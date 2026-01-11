import { createSecureTempFile, removeTempFile } from '../utils/tempFiles.js';

/**
 * Valid SSH key types that we support
 */
const VALID_KEY_TYPES = [
  'RSA PRIVATE KEY',
  'DSA PRIVATE KEY',
  'EC PRIVATE KEY',
  'PRIVATE KEY',
  'OPENSSH PRIVATE KEY',
] as const;

/**
 * Decodes and normalizes an SSH private key
 * - Accepts plain text
 * - Normalizes line endings to Unix format
 * - Validates key structure
 *
 * @param sshKey - Raw SSH key (plain text)
 * @returns Normalized SSH key with proper formatting
 * @throws Error if key is invalid
 */
export function decodeSSHKey(sshKey: string): string {
  if (!sshKey || sshKey.trim().length === 0) {
    throw new Error('SSH key is empty');
  }

  let key = sshKey.trim();

  if (!key.startsWith('-----BEGIN')) {
    throw new Error('SSH key must be in PEM format (should start with -----BEGIN)');
  }

  // Normalize line endings to Unix format (required for SSH compatibility)
  key = key.replaceAll('\r\n', '\n').replaceAll('\r', '\n');

  // Ensure key ends with single newline
  key = `${key.replace(/\n+$/, '')}\n`;

  // Validate PEM markers
  if (!key.includes('-----BEGIN') || !key.includes('-----END')) {
    throw new Error('SSH key does not contain valid PEM markers');
  }

  // Validate key type
  const hasValidKeyType = VALID_KEY_TYPES.some((keyType) => key.includes(keyType));
  if (!hasValidKeyType) {
    throw new Error(`SSH key type not recognized. Supported types: ${VALID_KEY_TYPES.join(', ')}`);
  }

  return key;
}

/**
 * Creates a temporary SSH key file with proper permissions
 *
 * @param sshKey - SSH private key content (plain text)
 * @returns Path to the temporary key file
 */
export async function createTempSSHKeyFile(sshKey: string): Promise<string> {
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
 * SSH key info extracted from vault
 */
export interface ExtractedKeyInfo {
  privateKey: string;
  keyType: string;
}

/**
 * Extracts and analyzes SSH key information
 *
 * @param sshKey - Raw SSH key
 * @returns Key information including type and encoding
 */
export function extractKeyInfo(sshKey: string): ExtractedKeyInfo {
  const decodedKey = decodeSSHKey(sshKey);

  // Extract key type from PEM header
  const keyTypeMatch = /-----BEGIN\s+(.+?)\s*-----/.exec(decodedKey);
  const keyType = keyTypeMatch ? keyTypeMatch[1] : 'UNKNOWN';

  return {
    privateKey: decodedKey,
    keyType,
  };
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
