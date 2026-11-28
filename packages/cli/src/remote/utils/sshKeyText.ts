/**
 * SSH private key TEXT: validation and normalisation, with no connection, agent or file I/O.
 *
 * Kept apart from remote/ssh because remote/ssh is a machine-plane marker for check:ci-command-planes:
 * a config-only writer such as remote/vscode/keyPersistence.ts needs the same normalisation, and
 * importing it from remote/ssh made every domain that reaches the config service read as machine-touching.
 */

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
