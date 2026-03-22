import { describe, expect, it } from 'vitest';
import {
  decrypt,
  deriveAesKey,
  deriveSharedSecret,
  encrypt,
  fromBase64,
  generateEphemeralKeyPair,
  importX25519PrivateKey,
  importX25519PublicKey,
  toBase64,
} from '../crypto.js';

// Fixed test keys (same as test-db.ts)
const TEST_X25519_PRIVATE_PKCS8 =
  'MC4CAQAwBQYDK2VuBCIEICiSVw3fU8IlyE5cO4+51WmfdH1D2mFk5QIxrVYiz117';
const TEST_X25519_PUBLIC_SPKI = 'MCowBQYDK2VuAyEAjX5clh+N8I3DnQU7e6JvuJHJUGBuVb32HrvKLPe4IB4=';

describe('E2E Crypto', () => {
  describe('Key Operations', () => {
    it('should generate an ephemeral key pair with 32-byte public key', async () => {
      const kp = await generateEphemeralKeyPair();
      expect(kp.privateKey).toBeDefined();
      expect(kp.publicKey).toBeDefined();
      expect(kp.publicKeyRaw).toBeInstanceOf(Uint8Array);
      expect(kp.publicKeyRaw.length).toBe(32);
    });

    it('should generate different key pairs on each call', async () => {
      const kp1 = await generateEphemeralKeyPair();
      const kp2 = await generateEphemeralKeyPair();
      expect(toBase64(kp1.publicKeyRaw)).not.toBe(toBase64(kp2.publicKeyRaw));
    });

    it('should import a valid SPKI X25519 public key', async () => {
      const key = await importX25519PublicKey(TEST_X25519_PUBLIC_SPKI);
      expect(key).toBeDefined();
      expect(key.type).toBe('public');
    });

    it('should import a valid PKCS8 X25519 private key', async () => {
      const key = await importX25519PrivateKey(TEST_X25519_PRIVATE_PKCS8);
      expect(key).toBeDefined();
      expect(key.type).toBe('private');
    });

    it('should throw on invalid base64 public key', async () => {
      await expect(importX25519PublicKey('not-valid-base64!!!')).rejects.toThrow();
    });
  });

  describe('Shared Secret Derivation', () => {
    it('should derive the same shared secret from both sides', async () => {
      const alice = await generateEphemeralKeyPair();
      const bob = await generateEphemeralKeyPair();

      const secretAlice = await deriveSharedSecret(alice.privateKey, bob.publicKey);
      const secretBob = await deriveSharedSecret(bob.privateKey, alice.publicKey);

      expect(toBase64(new Uint8Array(secretAlice))).toBe(toBase64(new Uint8Array(secretBob)));
    });

    it('should produce different shared secrets with different key pairs', async () => {
      const alice = await generateEphemeralKeyPair();
      const bob1 = await generateEphemeralKeyPair();
      const bob2 = await generateEphemeralKeyPair();

      const secret1 = await deriveSharedSecret(alice.privateKey, bob1.publicKey);
      const secret2 = await deriveSharedSecret(alice.privateKey, bob2.publicKey);

      expect(toBase64(new Uint8Array(secret1))).not.toBe(toBase64(new Uint8Array(secret2)));
    });
  });

  describe('AES-256-GCM', () => {
    async function makeAesKey(): Promise<CryptoKey> {
      const kp1 = await generateEphemeralKeyPair();
      const kp2 = await generateEphemeralKeyPair();
      const shared = await deriveSharedSecret(kp1.privateKey, kp2.publicKey);
      const salt = crypto.getRandomValues(new Uint8Array(16));
      return deriveAesKey(shared, salt);
    }

    it('should encrypt and decrypt a round-trip', async () => {
      const key = await makeAesKey();
      const plaintext = new TextEncoder().encode('Hello, E2E encryption!');
      const { iv, ct } = await encrypt(key, plaintext);
      const decrypted = await decrypt(key, iv, ct);
      expect(new TextDecoder().decode(decrypted)).toBe('Hello, E2E encryption!');
    });

    it('should handle empty plaintext', async () => {
      const key = await makeAesKey();
      const plaintext = new Uint8Array(0);
      const { iv, ct } = await encrypt(key, plaintext);
      const decrypted = await decrypt(key, iv, ct);
      expect(decrypted.length).toBe(0);
    });

    it('should handle large payloads (10KB)', async () => {
      const key = await makeAesKey();
      const plaintext = crypto.getRandomValues(new Uint8Array(10240));
      const { iv, ct } = await encrypt(key, plaintext);
      const decrypted = await decrypt(key, iv, ct);
      expect(toBase64(decrypted)).toBe(toBase64(plaintext));
    });

    it('should handle unicode content', async () => {
      const key = await makeAesKey();
      const text = 'Hello \u{1F512} encrypted \u{2764}\u{FE0F} world \u{1F30D}';
      const plaintext = new TextEncoder().encode(text);
      const { iv, ct } = await encrypt(key, plaintext);
      const decrypted = await decrypt(key, iv, ct);
      expect(new TextDecoder().decode(decrypted)).toBe(text);
    });

    it('should reject tampered ciphertext', async () => {
      const key = await makeAesKey();
      const plaintext = new TextEncoder().encode('sensitive data');
      const { iv, ct } = await encrypt(key, plaintext);

      // Flip a byte in the ciphertext
      const tampered = new Uint8Array(ct);
      tampered[0] ^= 0xff;

      await expect(decrypt(key, iv, tampered)).rejects.toThrow();
    });

    it('should reject decryption with wrong key', async () => {
      const key1 = await makeAesKey();
      const key2 = await makeAesKey();
      const plaintext = new TextEncoder().encode('sensitive data');
      const { iv, ct } = await encrypt(key1, plaintext);

      await expect(decrypt(key2, iv, ct)).rejects.toThrow();
    });

    it('should reject decryption with wrong IV', async () => {
      const key = await makeAesKey();
      const plaintext = new TextEncoder().encode('sensitive data');
      const { ct } = await encrypt(key, plaintext);

      const wrongIv = crypto.getRandomValues(new Uint8Array(12));
      await expect(decrypt(key, wrongIv, ct)).rejects.toThrow();
    });
  });

  describe('Key Derivation (HKDF)', () => {
    it('should be deterministic with same shared secret and salt', async () => {
      const kp1 = await generateEphemeralKeyPair();
      const kp2 = await generateEphemeralKeyPair();
      const shared = await deriveSharedSecret(kp1.privateKey, kp2.publicKey);
      const salt = crypto.getRandomValues(new Uint8Array(16));

      const key1 = await deriveAesKey(shared, salt);
      const key2 = await deriveAesKey(shared, salt);

      // Verify they produce the same encryption: encrypt with key1, decrypt with key2
      const plaintext = new TextEncoder().encode('deterministic test');
      const { iv, ct } = await encrypt(key1, plaintext);
      const decrypted = await decrypt(key2, iv, ct);
      expect(new TextDecoder().decode(decrypted)).toBe('deterministic test');
    });

    it('should produce different keys with different salts', async () => {
      const kp1 = await generateEphemeralKeyPair();
      const kp2 = await generateEphemeralKeyPair();
      const shared = await deriveSharedSecret(kp1.privateKey, kp2.publicKey);

      const salt1 = crypto.getRandomValues(new Uint8Array(16));
      const salt2 = crypto.getRandomValues(new Uint8Array(16));

      const key1 = await deriveAesKey(shared, salt1);
      const key2 = await deriveAesKey(shared, salt2);

      // Encrypt with key1, try decrypt with key2 — should fail
      const plaintext = new TextEncoder().encode('salt test');
      const { iv, ct } = await encrypt(key1, plaintext);
      await expect(decrypt(key2, iv, ct)).rejects.toThrow();
    });
  });

  describe('Base64 helpers', () => {
    it('should round-trip base64 encoding', () => {
      const original = crypto.getRandomValues(new Uint8Array(32));
      const encoded = toBase64(original);
      const decoded = fromBase64(encoded);
      expect(toBase64(decoded)).toBe(toBase64(original));
    });
  });
});
