import { encryptString, decryptString } from './encryption'

/**
 * Vault Protocol using VaultCompany as an encryption indicator
 * 
 * The protocol works as follows:
 * 1. VaultCompany is the Company's vault content returned during login
 * 2. If VaultCompany is encrypted (base64 pattern), all users must provide the master password
 * 3. The master password is stored in Redux and used to encrypt/decrypt vault fields
 * 4. The encrypted VaultCompany serves as an indicator that encryption is enabled
 * 5. All users in a company must use the same master password
 */

// Base64 pattern for encrypted values - matches output from encryptText
const ENCRYPTED_PATTERN = /^[A-Za-z0-9+/]+=*$/

/**
 * Check if a value appears to be encrypted
 * Encrypted values are base64 encoded and typically longer than the original
 */
export function isEncrypted(value: string | null | undefined): boolean {
  if (!value || value.length < 20) return false
  
  // Check if the value is valid JSON (not encrypted)
  try {
    JSON.parse(value)
    // If it parses as JSON, it's not encrypted
    return false
  } catch {
    // Not valid JSON, continue checking if it's encrypted
  }
  
  // Check if it matches base64 pattern and has reasonable length
  // Encrypted values are typically much longer than originals due to IV + encrypted data
  return ENCRYPTED_PATTERN.test(value) && value.length >= 40
}

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
    const decrypted = await decryptString(encryptedVaultCompany, masterPassword)
    
    // If decryption succeeds, the password is valid
    // The decrypted content should be valid JSON (even if it's just {})
    try {
      JSON.parse(decrypted)
      return true
    } catch {
      // If it's not valid JSON after decryption, the password is wrong
      return false
    }
  } catch (error) {
    // Decryption failed - wrong password
    return false
  }
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
  const companyHasEncryption = isEncrypted(vaultCompany)
  
  if (!companyHasEncryption) {
    return userProvidedPassword 
      ? VaultProtocolState.PASSWORD_NOT_NEEDED 
      : VaultProtocolState.NOT_ENABLED
  }
  
  if (!userProvidedPassword) {
    return VaultProtocolState.PASSWORD_REQUIRED
  }
  
  if (passwordValid === false || passwordValid === undefined) {
    return VaultProtocolState.INVALID_PASSWORD
  }
  
  return VaultProtocolState.VALID
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
    timestamp: new Date().toISOString()
  }
  
  // Encrypt the sentinel using the master password
  const encryptedSentinel = await encryptString(JSON.stringify(sentinel), masterPassword)
  return encryptedSentinel
}

/**
 * Get user-friendly message for vault protocol state
 * Note: This returns message keys for i18n translation
 */
export function getVaultProtocolMessage(state: VaultProtocolState): {
  type: 'error' | 'warning' | 'info' | 'success'
  messageKey: string
  message: string // Fallback message
} {
  switch (state) {
    case VaultProtocolState.NOT_ENABLED:
      return {
        type: 'info',
        messageKey: 'auth:login.errors.companyNotEncrypted',
        message: 'Your company has not enabled vault encryption'
      }
    
    case VaultProtocolState.PASSWORD_REQUIRED:
      return {
        type: 'error',
        messageKey: 'auth:login.errors.masterPasswordRequired',
        message: 'Your company requires a master password for vault encryption. Please enter the company master password.'
      }
    
    case VaultProtocolState.INVALID_PASSWORD:
      return {
        type: 'error',
        messageKey: 'auth:login.errors.invalidMasterPassword',
        message: 'Invalid master password. Please check with your administrator for the correct company master password.'
      }
    
    case VaultProtocolState.VALID:
      return {
        type: 'success',
        messageKey: 'common:messages.success',
        message: 'Master password validated successfully'
      }
    
    case VaultProtocolState.PASSWORD_NOT_NEEDED:
      return {
        type: 'warning',
        messageKey: 'auth:login.errors.companyNotEncrypted',
        message: 'Your company has not enabled vault encryption yet. The master password you entered will not be used.'
      }
    
    default:
      return {
        type: 'info',
        messageKey: '',
        message: ''
      }
  }
}