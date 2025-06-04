import { createHash } from 'crypto'
import { secureStorage } from './secureMemoryStorage'

export function hashPassword(password: string): string {
  // For browser compatibility, we'll use Web Crypto API
  return '0x' + Array.from(
    new Uint8Array(
      crypto.subtle.digestSync('SHA-256', new TextEncoder().encode(password))
    )
  ).map(b => b.toString(16).padStart(2, '0')).join('')
}

// Alternative using async Web Crypto API
export async function hashPasswordAsync(password: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(password)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
  return '0x' + hashHex
}

export function base64HashPassword(password: string): string {
  // Synchronous version for immediate use
  const hashHex = Array.from(
    new Uint8Array(
      crypto.subtle.digestSync?.('SHA-256', new TextEncoder().encode(password)) || []
    )
  ).map(b => b.toString(16).padStart(2, '0')).join('')
  
  const bytes = new Uint8Array(hashHex.match(/.{1,2}/g)?.map(byte => parseInt(byte, 16)) || [])
  return btoa(String.fromCharCode(...bytes))
}

// Session storage helpers using secure memory storage
export function saveAuthData(token: string, email: string, company?: string) {
  secureStorage.setItem('auth_token', token)
  secureStorage.setItem('user_email', email)
  if (company) {
    secureStorage.setItem('user_company', company)
  }
}

export function getAuthData() {
  return {
    token: secureStorage.getItem('auth_token'),
    email: secureStorage.getItem('user_email'),
    company: secureStorage.getItem('user_company'),
  }
}

export function clearAuthData() {
  secureStorage.removeItem('auth_token')
  secureStorage.removeItem('user_email')
  secureStorage.removeItem('user_company')
}

// Migration helper to move existing localStorage data to secure storage
export function migrateFromLocalStorage() {
  const token = localStorage.getItem('auth_token')
  const email = localStorage.getItem('user_email')
  const company = localStorage.getItem('user_company')
  
  if (token || email || company) {
    // Save to secure storage
    if (token) secureStorage.setItem('auth_token', token)
    if (email) secureStorage.setItem('user_email', email)
    if (company) secureStorage.setItem('user_company', company)
    
    // Clear from localStorage
    localStorage.removeItem('auth_token')
    localStorage.removeItem('user_email')
    localStorage.removeItem('user_company')
  }
}