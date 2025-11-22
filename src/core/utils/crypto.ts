import type { ICryptoProvider } from '../types'

export class CryptoService {
  constructor(private readonly provider: ICryptoProvider) {}

  encryptString(plaintext: string, password: string): Promise<string> {
    return this.provider.encrypt(plaintext, password)
  }

  decryptString(ciphertext: string, password: string): Promise<string> {
    return this.provider.decrypt(ciphertext, password)
  }

  async encryptVaultFields<T>(value: T, password: string): Promise<T> {
    if (!password || value === null || value === undefined) {
      return value
    }
    return this.transformVaultFields(value, password, (input) => this.encryptString(input, password))
  }

  async decryptVaultFields<T>(value: T, password: string): Promise<T> {
    if (!password || value === null || value === undefined) {
      return value
    }
    return this.transformVaultFields(value, password, (input) => this.tryDecrypt(input, password))
  }

  hasVaultFields(data: unknown): boolean {
    if (!data) return false
    if (Array.isArray(data)) {
      return data.some((item) => this.hasVaultFields(item))
    }
    if (typeof data === 'object') {
      return Object.keys(data as Record<string, unknown>).some((key) => {
        if (this.isVaultField(key)) return true
        const nested = (data as Record<string, unknown>)[key]
        return this.hasVaultFields(nested)
      })
    }
    return false
  }

  isAvailable(): boolean {
    return typeof this.provider.encrypt === 'function' && typeof this.provider.decrypt === 'function'
  }

  private async transformVaultFields<T>(
    value: T,
    password: string,
    transformer: (input: string) => Promise<string>,
  ): Promise<T> {
    if (Array.isArray(value)) {
      const result = await Promise.all(value.map((item) => this.transformVaultFields(item, password, transformer)))
      return result as T
    }

    if (typeof value === 'object' && value !== null) {
      const target: Record<string, unknown> = {}
      const entries = Object.entries(value as Record<string, unknown>)
      await Promise.all(
        entries.map(async ([key, entryValue]) => {
          if (this.shouldTransformField(key, entryValue)) {
            target[key] = await transformer(entryValue as string)
          } else if (Array.isArray(entryValue) || (entryValue && typeof entryValue === 'object')) {
            target[key] = await this.transformVaultFields(entryValue, password, transformer)
          } else {
            target[key] = entryValue
          }
        }),
      )
      return target as T
    }

    return value
  }

  private shouldTransformField(key: string, value: unknown): value is string {
    return this.isVaultField(key) && typeof value === 'string' && value.length > 0
  }

  private isVaultField(key: string): boolean {
    return key.toLowerCase().includes('vault')
  }

  private async tryDecrypt(value: string, password: string): Promise<string> {
    if (!this.isBase64Encrypted(value)) {
      return value
    }
    try {
      return await this.decryptString(value, password)
    } catch {
      return value
    }
  }

  private isBase64Encrypted(value: string): boolean {
    return /^[A-Za-z0-9+/]+=*$/.test(value)
  }
}

export class SecureMemoryStorage {
  private storage = new Map<string, string>()
  private masterPassword: string

  constructor(private readonly cryptoService: CryptoService) {
    this.masterPassword = this.generateMasterPassword()
  }

  async setItem(key: string, value: string): Promise<void> {
    if (!value) return
    const encrypted = await this.cryptoService.encryptString(value, this.masterPassword)
    this.storage.set(key, encrypted)
  }

  async getItem(key: string): Promise<string | null> {
    const encrypted = this.storage.get(key)
    if (!encrypted) return null
    try {
      const decrypted = await this.cryptoService.decryptString(encrypted, this.masterPassword)
      return decrypted || null
    } catch {
      return null
    }
  }

  removeItem(key: string): void {
    this.storage.delete(key)
  }

  clear(): void {
    this.storage.clear()
    this.masterPassword = this.generateMasterPassword()
  }

  hasItem(key: string): boolean {
    return this.storage.has(key)
  }

  keys(): string[] {
    return Array.from(this.storage.keys())
  }

  secureWipe(): void {
    this.storage.clear()
    this.masterPassword = ''.padEnd(this.masterPassword.length, '0')
  }

  private generateMasterPassword(): string {
    const bytes = this.getRandomValues(32)
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  }

  private getRandomValues(length: number): Uint8Array {
    if (typeof globalThis.crypto !== 'undefined' && typeof globalThis.crypto.getRandomValues === 'function') {
      return globalThis.crypto.getRandomValues(new Uint8Array(length))
    }
    const buffer = new Uint8Array(length)
    for (let i = 0; i < length; i += 1) {
      buffer[i] = Math.floor(Math.random() * 256)
    }
    return buffer
  }
}
