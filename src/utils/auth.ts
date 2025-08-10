// Authentication and password utilities for browser environment
import { secureStorage } from './secureMemoryStorage'
import { tokenService } from '@/services/tokenService'

// Static salt for password hashing - provides additional protection against dictionary attacks
// This salt is concatenated with the password before hashing to ensure even common passwords
// produce unique hashes. The salt value must be consistent across all components.
const STATIC_SALT = 'Rd!@cc111$ecur3P@$$w0rd$@lt#H@$h'

// Storage keys constants
const STORAGE_KEYS = {
  USER_EMAIL: 'user_email',
  USER_COMPANY: 'user_company',
  AUTH_TOKEN: 'auth_token'
} as const

// Password hashing using Web Crypto API with static salt
export async function hashPassword(password: string): Promise<string> {
  const encoder = new TextEncoder()
  // Concatenate password with static salt before hashing
  const saltedPassword = password + STATIC_SALT
  const data = encoder.encode(saltedPassword)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
  return '0x' + hashHex
}

// Session storage helpers using secure memory storage
export async function saveAuthData(token: string, email: string, company?: string) {
  // Use token service for token storage (provides additional security)
  await tokenService.setToken(token)
  // Store email and company in secure storage
  await secureStorage.setItem(STORAGE_KEYS.USER_EMAIL, email)
  if (company) {
    await secureStorage.setItem(STORAGE_KEYS.USER_COMPANY, company)
  }
}

export async function getAuthData() {
  const [token, email, company] = await Promise.all([
    tokenService.getToken(),
    secureStorage.getItem(STORAGE_KEYS.USER_EMAIL),
    secureStorage.getItem(STORAGE_KEYS.USER_COMPANY),
  ])
  
  return { token, email, company }
}

export function clearAuthData() {
  // Clear token using token service
  tokenService.clearToken()
  // Clear other auth data
  secureStorage.removeItem(STORAGE_KEYS.USER_EMAIL)
  secureStorage.removeItem(STORAGE_KEYS.USER_COMPANY)
}

// Helper function for batch storage operations
async function batchStorageOperation(
  source: Storage, 
  keys: Record<string, string>,
  operation: 'migrate' | 'clear'
) {
  const entries = Object.entries(keys)
  const values = entries.map(([_, key]) => source.getItem(key))
  
  if (operation === 'migrate') {
    // Save non-null values to secure storage
    await Promise.all(
      entries.map(([storageKey], index) => {
        const value = values[index]
        return value ? secureStorage.setItem(storageKey, value) : null
      }).filter(Boolean)
    )
  }
  
  // Clear from source storage
  entries.forEach(([_, key]) => source.removeItem(key))
}

// Migration helper to move existing localStorage data to secure storage
export async function migrateFromLocalStorage() {
  const migrationKeys = {
    [STORAGE_KEYS.AUTH_TOKEN]: STORAGE_KEYS.AUTH_TOKEN,
    [STORAGE_KEYS.USER_EMAIL]: STORAGE_KEYS.USER_EMAIL,
    [STORAGE_KEYS.USER_COMPANY]: STORAGE_KEYS.USER_COMPANY
  }
  
  // Check if migration is needed
  const hasData = Object.values(migrationKeys).some(key => localStorage.getItem(key))
  if (hasData) {
    await batchStorageOperation(localStorage, migrationKeys, 'migrate')
  }
}