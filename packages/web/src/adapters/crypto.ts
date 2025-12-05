import type { ICryptoProvider } from '@/core/types';

const ENCRYPTION_CONFIG = {
  SALT_LENGTH: 16,
  ITERATIONS: 100000,
  KEY_LENGTH: 256,
  IV_LENGTH: 12,
  TAG_LENGTH: 16,
} as const;

class WebCryptoProvider implements ICryptoProvider {
  async encrypt(data: string, password: string): Promise<string> {
    const salt = this.generateSalt();
    const key = await this.deriveKey(password, salt);
    const ivBytes = this.generateInitializationVector();
    const ivBuffer = this.toArrayBuffer(ivBytes);
    const encoded = new TextEncoder().encode(data);
    const plaintextBuffer = this.toArrayBuffer(encoded);
    const ciphertext = await crypto.subtle.encrypt(
      {
        name: 'AES-GCM',
        iv: ivBuffer,
        tagLength: ENCRYPTION_CONFIG.TAG_LENGTH * 8,
      },
      key,
      plaintextBuffer
    );

    const combined = new Uint8Array(salt.length + ivBytes.length + ciphertext.byteLength);
    combined.set(salt, 0);
    combined.set(ivBytes, salt.length);
    combined.set(new Uint8Array(ciphertext), salt.length + ivBytes.length);
    return this.arrayToBase64(combined);
  }

  async decrypt(data: string, password: string): Promise<string> {
    const combined = this.base64ToArray(data);
    const { salt, iv, ciphertext } = this.extractComponents(combined);
    const key = await this.deriveKey(password, salt);
    const cipherBuffer = this.toArrayBuffer(ciphertext);
    const decrypted = await crypto.subtle.decrypt(
      {
        name: 'AES-GCM',
        iv: this.toArrayBuffer(iv),
        tagLength: ENCRYPTION_CONFIG.TAG_LENGTH * 8,
      },
      key,
      cipherBuffer
    );
    return new TextDecoder().decode(decrypted);
  }

  async deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey> {
    const passwordBuffer = new TextEncoder().encode(password);
    const baseKey = await crypto.subtle.importKey('raw', passwordBuffer, 'PBKDF2', false, [
      'deriveBits',
      'deriveKey',
    ]);

    const saltBuffer = this.toArrayBuffer(salt);

    return crypto.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt: saltBuffer,
        iterations: ENCRYPTION_CONFIG.ITERATIONS,
        hash: 'SHA-256',
      },
      baseKey,
      { name: 'AES-GCM', length: ENCRYPTION_CONFIG.KEY_LENGTH },
      false,
      ['encrypt', 'decrypt']
    );
  }

  async generateHash(data: string): Promise<string> {
    const encoded = new TextEncoder().encode(data);
    const digest = await crypto.subtle.digest('SHA-256', encoded);
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, '0'))
      .join('');
  }

  private generateSalt(): Uint8Array {
    return crypto.getRandomValues(new Uint8Array(ENCRYPTION_CONFIG.SALT_LENGTH));
  }

  private generateInitializationVector(): Uint8Array {
    return crypto.getRandomValues(new Uint8Array(ENCRYPTION_CONFIG.IV_LENGTH));
  }

  private extractComponents(buffer: Uint8Array) {
    const salt = buffer.slice(0, ENCRYPTION_CONFIG.SALT_LENGTH);
    const iv = buffer.slice(
      ENCRYPTION_CONFIG.SALT_LENGTH,
      ENCRYPTION_CONFIG.SALT_LENGTH + ENCRYPTION_CONFIG.IV_LENGTH
    );
    const ciphertext = buffer.slice(ENCRYPTION_CONFIG.SALT_LENGTH + ENCRYPTION_CONFIG.IV_LENGTH);
    return { salt, iv, ciphertext };
  }

  private arrayToBase64(array: Uint8Array): string {
    let str = '';
    const chunkSize = 8192;
    for (let i = 0; i < array.length; i += chunkSize) {
      str += String.fromCharCode.apply(null, Array.from(array.subarray(i, i + chunkSize)));
    }
    return btoa(str);
  }

  private base64ToArray(base64: string): Uint8Array {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }

  private toArrayBuffer(view: Uint8Array): ArrayBuffer {
    const buffer = new ArrayBuffer(view.byteLength);
    new Uint8Array(buffer).set(view);
    return buffer;
  }
}

export const webCryptoProvider = new WebCryptoProvider();
export default webCryptoProvider;
