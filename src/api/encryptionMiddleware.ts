import { encryptVaultFields, decryptVaultFields } from '../utils/encryption'
import { masterPasswordService } from '../services/masterPasswordService'
import { showMessage } from '../utils/messages'

/**
 * Middleware to handle vault field encryption/decryption
 * Applied to axios request/response interceptors
 */

/**
 * Encrypts vault fields in request data before sending
 */
export async function encryptRequestData(data: any): Promise<any> {
  const masterPassword = await masterPasswordService.getMasterPassword()
  
  if (!masterPassword || !data) {
    return data
  }

  try {
    return await encryptVaultFields(data, masterPassword)
  } catch (error) {
    console.error('Failed to encrypt request data:', error)
    showMessage('error', 'Failed to encrypt secure data')
    throw error
  }
}

/**
 * Decrypts vault fields in response data after receiving
 */
export async function decryptResponseData(data: any): Promise<any> {
  const masterPassword = await masterPasswordService.getMasterPassword()
  
  if (!masterPassword || !data) {
    return data
  }

  try {
    return await decryptVaultFields(data, masterPassword)
  } catch (error) {
    console.error('Failed to decrypt response data:', error)
    showMessage('error', 'Failed to decrypt secure data - check your master password')
    // Return original data instead of throwing to allow app to continue
    return data
  }
}

/**
 * Checks if any vault fields exist in the object
 */
export function hasVaultFields(data: any): boolean {
  if (!data || typeof data !== 'object') return false

  return checkObjectForVaultFields(data)
}

function checkObjectForVaultFields(object: any): boolean {
  for (const key in object) {
    if (key.toLowerCase().includes('vault')) {
      return true
    }
    
    const value = object[key]
    if (typeof value === 'object' && value !== null) {
      if (checkObjectForVaultFields(value)) {
        return true
      }
    }
  }
  return false
}