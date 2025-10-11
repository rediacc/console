/**
 * Secure in-memory storage with AES-GCM encryption for sensitive authentication data
 * This replaces localStorage to prevent token theft from browser storage
 */

interface EncryptedData {
  ciphertext: string;
  iv: string;
  salt: string;
}

class SecureMemoryStorage {
  private storage: Map<string, EncryptedData> = new Map();
  private masterPassword: string;

  constructor() {
    // Generate a random master password for this session
    this.masterPassword = this.generateMasterPassword();
  }

  /**
   * Generate a cryptographically secure random master password
   */
  private generateMasterPassword(): string {
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
  }

  /**
   * Derive a cryptographic key from the master password using PBKDF2
   */
  private async deriveKey(salt: Uint8Array): Promise<CryptoKey> {
    const encoder = new TextEncoder();
    const keyMaterial = await crypto.subtle.importKey(
      'raw',
      encoder.encode(this.masterPassword),
      'PBKDF2',
      false,
      ['deriveBits', 'deriveKey']
    );

    return crypto.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt: salt,
        iterations: 100000, // OWASP recommended minimum
        hash: 'SHA-256'
      },
      keyMaterial,
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt']
    );
  }

  /**
   * Encrypt text using AES-GCM with authenticated encryption
   */
  private async encrypt(text: string): Promise<EncryptedData> {
    if (!text) return { ciphertext: '', iv: '', salt: '' };

    try {
      // Generate random salt for key derivation
      const salt = crypto.getRandomValues(new Uint8Array(16));
      
      // Derive key from master password
      const key = await this.deriveKey(salt);
      
      // Generate random IV for AES-GCM
      const iv = crypto.getRandomValues(new Uint8Array(12));
      
      // Encode text to bytes
      const encoder = new TextEncoder();
      const data = encoder.encode(text);
      
      // Encrypt with AES-GCM
      const ciphertext = await crypto.subtle.encrypt(
        {
          name: 'AES-GCM',
          iv: iv
        },
        key,
        data
      );
      
      // Return encrypted data with metadata
      return {
        ciphertext: btoa(String.fromCharCode(...new Uint8Array(ciphertext))),
        iv: btoa(String.fromCharCode(...iv)),
        salt: btoa(String.fromCharCode(...salt))
      };
    } catch (error) {
      throw new Error('Failed to encrypt data');
    }
  }

  /**
   * Decrypt AES-GCM encrypted text with authentication
   */
  private async decrypt(encryptedData: EncryptedData): Promise<string> {
    if (!encryptedData.ciphertext) return '';

    try {
      // Decode from base64
      const ciphertext = Uint8Array.from(atob(encryptedData.ciphertext), c => c.charCodeAt(0));
      const iv = Uint8Array.from(atob(encryptedData.iv), c => c.charCodeAt(0));
      const salt = Uint8Array.from(atob(encryptedData.salt), c => c.charCodeAt(0));
      
      // Derive key from master password
      const key = await this.deriveKey(salt);
      
      // Decrypt with AES-GCM (includes authentication)
      const decrypted = await crypto.subtle.decrypt(
        {
          name: 'AES-GCM',
          iv: iv
        },
        key,
        ciphertext
      );
      
      // Decode bytes to text
      const decoder = new TextDecoder();
      return decoder.decode(decrypted);
    } catch (error) {
      // Authentication failure or tampering detected
      return '';
    }
  }

  /**
   * Store encrypted value in memory
   */
  async setItem(key: string, value: string): Promise<void> {
    if (value) {
      const encrypted = await this.encrypt(value);
      this.storage.set(key, encrypted);
    }
  }

  /**
   * Retrieve and decrypt value from memory
   */
  async getItem(key: string): Promise<string | null> {
    const encrypted = this.storage.get(key);
    if (!encrypted) return null;
    const decrypted = await this.decrypt(encrypted);
    return decrypted || null;
  }

  /**
   * Remove item from memory
   */
  removeItem(key: string): void {
    this.storage.delete(key);
  }

  /**
   * Clear all stored data and regenerate master password
   */
  clear(): void {
    this.storage.clear();
    // Regenerate master password for additional security
    this.masterPassword = this.generateMasterPassword();
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

  /**
   * Secure wipe of sensitive data from memory
   */
  secureWipe(): void {
    // Clear storage
    this.storage.clear();

    // Overwrite master password
    const length = this.masterPassword.length;
    this.masterPassword = '0'.repeat(length);
    this.masterPassword = '';
  }
}

// Create a singleton instance
export const secureStorage = new SecureMemoryStorage();

// Export storage interface for type safety
export interface ISecureStorage {
  setItem(key: string, value: string): Promise<void>;
  getItem(key: string): Promise<string | null>;
  removeItem(key: string): void;
  clear(): void;
  hasItem(key: string): boolean;
  secureWipe(): void;
}

// Auto-wipe on page unload for security
if (typeof window !== 'undefined') {
  let isProtocolLaunch = false;

  // Track protocol launches to avoid wiping tokens
  window.addEventListener('beforeunload', (_event) => {
    // Don't wipe if this is just a protocol launch
    if (isProtocolLaunch) {
      isProtocolLaunch = false;
      return;
    }

    // Only wipe on actual page navigation/close
    secureStorage.secureWipe();
  });

  // Export function for protocolUrlService to signal protocol launches
  (window as any).signalProtocolLaunch = () => {
    isProtocolLaunch = true;
    // Reset flag after a brief delay to handle the event
    setTimeout(() => { isProtocolLaunch = false; }, 100);
  };
}