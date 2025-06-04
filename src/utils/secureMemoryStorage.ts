/**
 * Secure in-memory storage with encryption for sensitive authentication data
 * This replaces localStorage to prevent token theft from browser storage
 */

class SecureMemoryStorage {
  private storage: Map<string, string> = new Map();
  private encryptionKey: string;

  constructor() {
    // Generate a random encryption key for this session
    this.encryptionKey = this.generateKey();
  }

  /**
   * Generate a random key for encryption
   */
  private generateKey(): string {
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
  }

  /**
   * Simple XOR encryption (can be replaced with more robust encryption)
   */
  private encrypt(text: string): string {
    if (!text) return '';
    
    let encrypted = '';
    for (let i = 0; i < text.length; i++) {
      const charCode = text.charCodeAt(i) ^ this.encryptionKey.charCodeAt(i % this.encryptionKey.length);
      encrypted += String.fromCharCode(charCode);
    }
    return btoa(encrypted); // Base64 encode for safe storage
  }

  /**
   * Decrypt XOR encrypted text
   */
  private decrypt(encryptedText: string): string {
    if (!encryptedText) return '';
    
    try {
      const encrypted = atob(encryptedText); // Base64 decode
      let decrypted = '';
      for (let i = 0; i < encrypted.length; i++) {
        const charCode = encrypted.charCodeAt(i) ^ this.encryptionKey.charCodeAt(i % this.encryptionKey.length);
        decrypted += String.fromCharCode(charCode);
      }
      return decrypted;
    } catch {
      return '';
    }
  }

  /**
   * Store encrypted value in memory
   */
  setItem(key: string, value: string): void {
    if (value) {
      this.storage.set(key, this.encrypt(value));
    }
  }

  /**
   * Retrieve and decrypt value from memory
   */
  getItem(key: string): string | null {
    const encrypted = this.storage.get(key);
    if (!encrypted) return null;
    return this.decrypt(encrypted);
  }

  /**
   * Remove item from memory
   */
  removeItem(key: string): void {
    this.storage.delete(key);
  }

  /**
   * Clear all stored data
   */
  clear(): void {
    this.storage.clear();
  }

  /**
   * Check if a key exists
   */
  hasItem(key: string): boolean {
    return this.storage.has(key);
  }

  /**
   * Get all keys (for debugging purposes)
   */
  keys(): string[] {
    return Array.from(this.storage.keys());
  }
}

// Create a singleton instance
export const secureStorage = new SecureMemoryStorage();

// Export storage interface for type safety
export interface ISecureStorage {
  setItem(key: string, value: string): void;
  getItem(key: string): string | null;
  removeItem(key: string): void;
  clear(): void;
  hasItem(key: string): boolean;
}