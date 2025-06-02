import { createHash } from 'crypto'

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

// Session storage helpers
export function saveAuthData(token: string, email: string, company?: string) {
  localStorage.setItem('auth_token', token)
  localStorage.setItem('user_email', email)
  if (company) {
    localStorage.setItem('user_company', company)
  }
}

export function getAuthData() {
  return {
    token: localStorage.getItem('auth_token'),
    email: localStorage.getItem('user_email'),
    company: localStorage.getItem('user_company'),
  }
}

export function clearAuthData() {
  localStorage.removeItem('auth_token')
  localStorage.removeItem('user_email')
  localStorage.removeItem('user_company')
}