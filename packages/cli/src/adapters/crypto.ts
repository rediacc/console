import { createCipheriv, createDecipheriv, pbkdf2, randomBytes } from 'node:crypto';
import { promisify } from 'node:util';
import type { ICryptoProvider } from '@rediacc/shared/encryption';
import { ENCRYPTION_CONFIG } from '@rediacc/shared/encryption';

const pbkdf2Async = promisify(pbkdf2);

/**
 * Per-blob password encryption: base64(salt + iv + ciphertext + tag), a fresh PBKDF2 per blob. The
 * blob does not record its iteration count, so every caller of `decrypt` must know it; the default is
 * `ENCRYPTION_CONFIG.LEGACY_ITERATIONS`, the count every existing blob and verifier was made with.
 * A sealed config's field blobs do not come through here (adapters/config-seal-key.ts derives one
 * key per process instead).
 */
class NodeCryptoProvider implements ICryptoProvider {
  async encrypt(
    data: string,
    password: string,
    iterations: number = ENCRYPTION_CONFIG.LEGACY_ITERATIONS
  ): Promise<string> {
    const salt = randomBytes(ENCRYPTION_CONFIG.SALT_LENGTH);
    const key = await this.deriveKeyBuffer(password, salt, iterations);
    const iv = randomBytes(ENCRYPTION_CONFIG.IV_LENGTH);

    const cipher = createCipheriv(ENCRYPTION_CONFIG.ALGORITHM, key, iv, {
      authTagLength: ENCRYPTION_CONFIG.TAG_LENGTH,
    });

    const encrypted = Buffer.concat([cipher.update(data, 'utf8'), cipher.final()]);

    const authTag = cipher.getAuthTag();

    // Combine: salt + iv + ciphertext + authTag Note: In web crypto, authTag is appended to ciphertext automatically
    const combined = Buffer.concat([salt, iv, encrypted, authTag]);

    return combined.toString('base64');
  }

  async decrypt(
    data: string,
    password: string,
    iterations: number = ENCRYPTION_CONFIG.LEGACY_ITERATIONS
  ): Promise<string> {
    const combined = Buffer.from(data, 'base64');

    const salt = combined.subarray(0, ENCRYPTION_CONFIG.SALT_LENGTH);
    const iv = combined.subarray(
      ENCRYPTION_CONFIG.SALT_LENGTH,
      ENCRYPTION_CONFIG.SALT_LENGTH + ENCRYPTION_CONFIG.IV_LENGTH
    );
    const authTag = combined.subarray(-ENCRYPTION_CONFIG.TAG_LENGTH);
    const ciphertext = combined.subarray(
      ENCRYPTION_CONFIG.SALT_LENGTH + ENCRYPTION_CONFIG.IV_LENGTH,
      -ENCRYPTION_CONFIG.TAG_LENGTH
    );

    const key = await this.deriveKeyBuffer(password, salt, iterations);

    const decipher = createDecipheriv(ENCRYPTION_CONFIG.ALGORITHM, key, iv, {
      authTagLength: ENCRYPTION_CONFIG.TAG_LENGTH,
    });

    decipher.setAuthTag(authTag);

    const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]);

    return decrypted.toString('utf8');
  }

  /** PBKDF2-SHA256 of `password` over `salt`, base64; `ENCRYPTION_CONFIG.ITERATIONS` (600k) unless told otherwise. */
  async deriveKey(
    password: string,
    salt: Uint8Array,
    iterations: number = ENCRYPTION_CONFIG.ITERATIONS
  ): Promise<string> {
    const key = await this.deriveKeyBuffer(password, Buffer.from(salt), iterations);
    return key.toString('base64');
  }

  /** PBKDF2-SHA256 of `password` over `salt` as raw key bytes. */
  deriveKeyBytes(
    password: string,
    salt: Uint8Array,
    iterations: number = ENCRYPTION_CONFIG.ITERATIONS
  ): Promise<Buffer> {
    return this.deriveKeyBuffer(password, Buffer.from(salt), iterations);
  }

  private deriveKeyBuffer(password: string, salt: Buffer, iterations: number): Promise<Buffer> {
    return pbkdf2Async(
      password,
      salt,
      iterations,
      ENCRYPTION_CONFIG.KEY_LENGTH_BYTES,
      ENCRYPTION_CONFIG.HASH
    );
  }
}

export const nodeCryptoProvider = new NodeCryptoProvider();
