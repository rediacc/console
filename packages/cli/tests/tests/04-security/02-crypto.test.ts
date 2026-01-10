import { expect, test } from '@playwright/test';
import { nodeCryptoProvider } from '../../../src/adapters/crypto.js';

test.describe('NodeCryptoProvider @cli @security', () => {
  const testPassword = 'test-master-password-123!';

  test.describe('encrypt/decrypt round-trip', () => {
    test('should encrypt and decrypt a simple string', async () => {
      const plaintext = 'Hello, World!';
      const encrypted = await nodeCryptoProvider.encrypt(plaintext, testPassword);
      const decrypted = await nodeCryptoProvider.decrypt(encrypted, testPassword);

      expect(decrypted).toBe(plaintext);
    });

    test('should encrypt and decrypt JSON object string', async () => {
      const data = JSON.stringify({ key: 'value', nested: { a: 1, b: [1, 2, 3] } });
      const encrypted = await nodeCryptoProvider.encrypt(data, testPassword);
      const decrypted = await nodeCryptoProvider.decrypt(encrypted, testPassword);

      expect(decrypted).toBe(data);
      expect(JSON.parse(decrypted)).toEqual(JSON.parse(data));
    });

    test('should encrypt and decrypt special characters', async () => {
      const plaintext = '!@#$%^&*()_+-=[]{}|;:,.<>?/~`"\'\\';
      const encrypted = await nodeCryptoProvider.encrypt(plaintext, testPassword);
      const decrypted = await nodeCryptoProvider.decrypt(encrypted, testPassword);

      expect(decrypted).toBe(plaintext);
    });

    test('should encrypt and decrypt unicode characters', async () => {
      const plaintext = '你好世界 مرحبا العالم 🌍🔐';
      const encrypted = await nodeCryptoProvider.encrypt(plaintext, testPassword);
      const decrypted = await nodeCryptoProvider.decrypt(encrypted, testPassword);

      expect(decrypted).toBe(plaintext);
    });

    test('should encrypt and decrypt empty string', async () => {
      const plaintext = '';
      const encrypted = await nodeCryptoProvider.encrypt(plaintext, testPassword);
      const decrypted = await nodeCryptoProvider.decrypt(encrypted, testPassword);

      expect(decrypted).toBe(plaintext);
    });

    test('should encrypt and decrypt large data', async () => {
      const plaintext = 'x'.repeat(10000);
      const encrypted = await nodeCryptoProvider.encrypt(plaintext, testPassword);
      const decrypted = await nodeCryptoProvider.decrypt(encrypted, testPassword);

      expect(decrypted).toBe(plaintext);
    });
  });

  test.describe('random salt/IV', () => {
    test('should produce different ciphertext each time for same input', async () => {
      const plaintext = 'Same input every time';
      const encrypted1 = await nodeCryptoProvider.encrypt(plaintext, testPassword);
      const encrypted2 = await nodeCryptoProvider.encrypt(plaintext, testPassword);
      const encrypted3 = await nodeCryptoProvider.encrypt(plaintext, testPassword);

      expect(encrypted1).not.toBe(encrypted2);
      expect(encrypted2).not.toBe(encrypted3);
      expect(encrypted1).not.toBe(encrypted3);

      // But all should decrypt to the same value
      expect(await nodeCryptoProvider.decrypt(encrypted1, testPassword)).toBe(plaintext);
      expect(await nodeCryptoProvider.decrypt(encrypted2, testPassword)).toBe(plaintext);
      expect(await nodeCryptoProvider.decrypt(encrypted3, testPassword)).toBe(plaintext);
    });
  });

  test.describe('error handling', () => {
    test('should fail with wrong password', async () => {
      const encrypted = await nodeCryptoProvider.encrypt('secret data', testPassword);

      await expect(nodeCryptoProvider.decrypt(encrypted, 'wrong-password')).rejects.toThrow();
    });

    test('should fail with empty password for decryption', async () => {
      const encrypted = await nodeCryptoProvider.encrypt('secret data', testPassword);

      await expect(nodeCryptoProvider.decrypt(encrypted, '')).rejects.toThrow();
    });

    test('should fail with corrupted base64 data', async () => {
      await expect(
        nodeCryptoProvider.decrypt('not-valid-base64!!!', testPassword)
      ).rejects.toThrow();
    });

    test('should fail with truncated ciphertext', async () => {
      const encrypted = await nodeCryptoProvider.encrypt('secret', testPassword);
      const truncated = encrypted.slice(0, 20);

      await expect(nodeCryptoProvider.decrypt(truncated, testPassword)).rejects.toThrow();
    });

    test('should fail with modified ciphertext (tampered data)', async () => {
      const encrypted = await nodeCryptoProvider.encrypt('secret', testPassword);
      // Modify a character in the middle
      const tampered =
        encrypted.slice(0, 30) + (encrypted[30] === 'A' ? 'B' : 'A') + encrypted.slice(31);

      await expect(nodeCryptoProvider.decrypt(tampered, testPassword)).rejects.toThrow();
    });
  });

  test.describe('encryption format', () => {
    test('should produce base64 output', async () => {
      const encrypted = await nodeCryptoProvider.encrypt('test', testPassword);

      expect(encrypted).toMatch(/^[A-Za-z0-9+/]+=*$/);
    });

    test('should produce output longer than 40 characters', async () => {
      const encrypted = await nodeCryptoProvider.encrypt('x', testPassword);
      // salt(16) + iv(12) + data + tag(16) = at least 44 bytes = 60+ base64 chars
      expect(encrypted.length).toBeGreaterThan(40);
    });

    test('should have consistent minimum output size', async () => {
      // Even for tiny input, output should include salt + iv + tag
      // 16 + 12 + 16 = 44 bytes minimum overhead
      const encrypted = await nodeCryptoProvider.encrypt('', testPassword);
      // 44 bytes in base64 = ~60 characters
      expect(encrypted.length).toBeGreaterThanOrEqual(56);
    });
  });

  test.describe('password hashing', () => {
    test('should generate consistent hash for same input', async () => {
      const hash1 = await nodeCryptoProvider.generateHash('password123');
      const hash2 = await nodeCryptoProvider.generateHash('password123');

      expect(hash1).toBe(hash2);
    });

    test('should generate different hashes for different inputs', async () => {
      const hash1 = await nodeCryptoProvider.generateHash('password1');
      const hash2 = await nodeCryptoProvider.generateHash('password2');

      expect(hash1).not.toBe(hash2);
    });

    test('should produce hex format with 0x prefix', async () => {
      const hash = await nodeCryptoProvider.generateHash('test');

      expect(hash).toMatch(/^0x[a-f0-9]{64}$/);
    });
  });

  test.describe('key derivation', () => {
    test('should derive key from password and salt', async () => {
      const salt = new Uint8Array(16).fill(1);
      const key = await nodeCryptoProvider.deriveKey('password', salt);

      expect(typeof key).toBe('string');
      expect(key.length).toBeGreaterThan(0);
    });

    test('should produce different keys for different salts', async () => {
      const salt1 = new Uint8Array(16).fill(1);
      const salt2 = new Uint8Array(16).fill(2);

      const key1 = await nodeCryptoProvider.deriveKey('password', salt1);
      const key2 = await nodeCryptoProvider.deriveKey('password', salt2);

      expect(key1).not.toBe(key2);
    });

    test('should produce different keys for different passwords', async () => {
      const salt = new Uint8Array(16).fill(1);

      const key1 = await nodeCryptoProvider.deriveKey('password1', salt);
      const key2 = await nodeCryptoProvider.deriveKey('password2', salt);

      expect(key1).not.toBe(key2);
    });
  });
});
