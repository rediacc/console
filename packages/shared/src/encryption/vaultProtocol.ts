/**
 * Vault Protocol utilities for encryption detection
 *
 * The protocol works as follows:
 * 1. VaultCompany is the Company's vault content returned during login
 * 2. If VaultCompany is encrypted (base64 pattern), all users must provide the master password
 * 3. The master password is stored in secure memory and used to encrypt/decrypt vault fields
 * 4. The encrypted VaultCompany serves as an indicator that encryption is enabled
 * 5. All users in a company must use the same master password
 */

// Base64 pattern for encrypted values - matches output from encryptText
const ENCRYPTED_PATTERN = /^[A-Za-z0-9+/]+=*$/;

/**
 * Check if a value appears to be encrypted
 * Encrypted values are base64 encoded and typically longer than the original
 */
export function isEncrypted(value: string | null | undefined): boolean {
  if (!value || value.length < 20) return false;

  // Check if the value is valid JSON (not encrypted)
  try {
    JSON.parse(value);
    // If it parses as JSON, it's not encrypted
    return false;
  } catch {
    // Not valid JSON, continue checking if it's encrypted
  }

  // Check if it matches base64 pattern and has reasonable length
  // Encrypted values are typically much longer than originals due to IV + encrypted data
  return ENCRYPTED_PATTERN.test(value) && value.length >= 40;
}

/**
 * Protocol states for UI feedback
 */
export enum VaultProtocolState {
  // Company has not enabled encryption
  NOT_ENABLED = 'NOT_ENABLED',
  // Company has encryption, user needs to provide password
  PASSWORD_REQUIRED = 'PASSWORD_REQUIRED',
  // Company has encryption, user provided wrong password
  INVALID_PASSWORD = 'INVALID_PASSWORD',
  // Company has encryption, password is valid
  VALID = 'VALID',
  // User provided password but company hasn't enabled encryption
  PASSWORD_NOT_NEEDED = 'PASSWORD_NOT_NEEDED',
}

/**
 * Analyze vault protocol state based on VaultCompany and user input
 */
export function analyzeVaultProtocolState(
  vaultCompany: string | null | undefined,
  userProvidedPassword: boolean,
  passwordValid?: boolean
): VaultProtocolState {
  const companyHasEncryption = isEncrypted(vaultCompany);

  if (!companyHasEncryption) {
    return userProvidedPassword
      ? VaultProtocolState.PASSWORD_NOT_NEEDED
      : VaultProtocolState.NOT_ENABLED;
  }

  if (!userProvidedPassword) {
    return VaultProtocolState.PASSWORD_REQUIRED;
  }

  if (!passwordValid) {
    return VaultProtocolState.INVALID_PASSWORD;
  }

  return VaultProtocolState.VALID;
}
