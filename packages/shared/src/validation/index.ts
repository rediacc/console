/**
 * Shared validation utilities
 */

/**
 * Validate GUID/UUID format
 * @param value - String to validate
 * @returns True if the string is a valid GUID
 */
export function isValidGuid(value: string): boolean {
  const guidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return guidRegex.test(value);
}

/**
 * Validate JSON string
 * @param jsonString - String to validate as JSON
 * @returns True if the string is valid JSON
 */
export function isValidJson(jsonString: string): boolean {
  try {
    JSON.parse(jsonString);
    return true;
  } catch {
    return false;
  }
}

/**
 * Validate email address format (RFC 5322 simplified)
 * @param email - Email string to validate
 * @returns True if the string is a valid email format
 */
export function isValidEmail(email: string): boolean {
  if (!email || typeof email !== 'string') return false;
  // RFC 5322 simplified pattern - covers most common email formats
  const emailPattern =
    /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;
  return emailPattern.test(email);
}

/**
 * Validate OTP/verification code format
 * @param code - The code string to validate
 * @param length - Expected code length (default: 6)
 * @returns True if the code matches the expected format (digits only)
 */
export function isValidOTPCode(code: string, length = 6): boolean {
  if (!code || typeof code !== 'string') return false;
  const pattern = new RegExp(`^\\d{${length}}$`);
  return pattern.test(code);
}

/**
 * Validate activation code format (alphanumeric)
 * @param code - The activation code string to validate
 * @param minLength - Minimum code length (default: 6)
 * @returns True if the code is alphanumeric with minimum length
 */
export function isValidActivationCode(code: string, minLength = 6): boolean {
  if (!code || typeof code !== 'string') return false;
  if (code.length < minLength) return false;
  const alphanumericPattern = /^[a-zA-Z0-9]+$/;
  return alphanumericPattern.test(code);
}

// Re-export network/SSH validators from queue-vault for convenience
export {
  formatSizeBytes,
  isValidHost,
  isValidHostname,
  isValidIP,
  isValidIPv4,
  isValidIPv6,
  isValidNetworkId,
  isValidPort,
  isValidSSHPrivateKey,
  parseSize,
  validateMachineVault,
  validateNetworkId,
  validateSize,
  validateSSHConnection,
  validateSSHPrivateKey,
} from '../queue-vault/utils/validation';
