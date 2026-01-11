import type { ICryptoProvider } from '@/platform/types';
import { createVaultEncryptor } from '@rediacc/shared/encryption';

export class CryptoService {
  private readonly vaultEncryptor;

  constructor(private readonly provider: ICryptoProvider) {
    this.vaultEncryptor = createVaultEncryptor(provider);
  }

  encryptString(plaintext: string, password: string): Promise<string> {
    return this.provider.encrypt(plaintext, password);
  }

  decryptString(ciphertext: string, password: string): Promise<string> {
    return this.provider.decrypt(ciphertext, password);
  }

  async encryptVaultFields<T>(value: T, password: string): Promise<T> {
    if (!password || value === null || value === undefined) {
      return value;
    }
    return this.vaultEncryptor.encrypt(value, password);
  }

  async decryptVaultFields<T>(value: T, password: string): Promise<T> {
    if (!password || value === null || value === undefined) {
      return value;
    }
    return this.vaultEncryptor.decrypt(value, password);
  }

  hasVaultFields(data: unknown): boolean {
    return this.vaultEncryptor.hasVaultFields(data);
  }

  isAvailable(): boolean {
    return (
      typeof this.provider.encrypt === 'function' && typeof this.provider.decrypt === 'function'
    );
  }
}

export class SecureMemoryStorage {
  private readonly storage = new Map<string, string>();
  private masterPassword: string;

  constructor(private readonly cryptoService: CryptoService) {
    this.masterPassword = this.generateMasterPassword();
  }

  async setItem(key: string, value: string): Promise<void> {
    if (!value) return;
    const encrypted = await this.cryptoService.encryptString(value, this.masterPassword);
    this.storage.set(key, encrypted);
  }

  async getItem(key: string): Promise<string | null> {
    const encrypted = this.storage.get(key);
    if (!encrypted) return null;
    try {
      const decrypted = await this.cryptoService.decryptString(encrypted, this.masterPassword);
      return decrypted || null;
    } catch {
      return null;
    }
  }

  removeItem(key: string): void {
    this.storage.delete(key);
  }

  clear(): void {
    this.storage.clear();
    this.masterPassword = this.generateMasterPassword();
  }

  hasItem(key: string): boolean {
    return this.storage.has(key);
  }

  keys(): string[] {
    return Array.from(this.storage.keys());
  }

  secureWipe(): void {
    this.storage.clear();
    this.masterPassword = ''.padEnd(this.masterPassword.length, '0');
  }

  private generateMasterPassword(): string {
    const bytes = this.getRandomValues(32);
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  }

  private getRandomValues(length: number): Uint8Array {
    if (
      typeof globalThis.crypto !== 'undefined' &&
      typeof globalThis.crypto.getRandomValues === 'function'
    ) {
      return globalThis.crypto.getRandomValues(new Uint8Array(length));
    }
    const buffer = new Uint8Array(length);
    for (let i = 0; i < length; i += 1) {
      buffer[i] = Math.floor(Math.random() * 256);
    }
    return buffer;
  }
}
