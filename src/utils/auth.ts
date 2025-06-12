// Authentication and password utilities for browser environment
import { secureStorage } from './secureMemoryStorage'
import { tokenService } from '@/services/tokenService'

// Static salt for password hashing - provides additional protection against dictionary attacks
// This salt is concatenated with the password before hashing to ensure even common passwords
// produce unique hashes. The salt value must be consistent across all components.
const STATIC_SALT = 'Rd!@cc111$ecur3P@$$w0rd$@lt#H@$h'

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
  await secureStorage.setItem('user_email', email)
  if (company) {
    await secureStorage.setItem('user_company', company)
  }
}

export async function getAuthData() {
  const [token, email, company] = await Promise.all([
    tokenService.getToken(),
    secureStorage.getItem('user_email'),
    secureStorage.getItem('user_company'),
  ])
  
  return { token, email, company }
}

export function clearAuthData() {
  // Clear token using token service
  tokenService.clearToken()
  // Clear other auth data
  secureStorage.removeItem('user_email')
  secureStorage.removeItem('user_company')
}

// Migration helper to move existing localStorage data to secure storage
export async function migrateFromLocalStorage() {
  const token = localStorage.getItem('auth_token')
  const email = localStorage.getItem('user_email')
  const company = localStorage.getItem('user_company')
  
  if (token || email || company) {
    // Save to secure storage
    if (token) await secureStorage.setItem('auth_token', token)
    if (email) await secureStorage.setItem('user_email', email)
    if (company) await secureStorage.setItem('user_company', company)
    
    // Clear from localStorage
    localStorage.removeItem('auth_token')
    localStorage.removeItem('user_email')
    localStorage.removeItem('user_company')
  }
}