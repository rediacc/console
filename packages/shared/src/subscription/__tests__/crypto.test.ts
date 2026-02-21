import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { PLAN_FEATURES, PLAN_RESOURCES } from '../constants.js';
import {
  clearPublicKeys,
  createSignedSubscription,
  generateKeyPair,
  getPublicKeyIds,
  hasPublicKey,
  importPrivateKey,
  importPublicKey,
  signSubscriptionPayload,
  verifyAndDecodeSubscription,
  verifySignature,
} from '../crypto.js';
import { encodeSubscriptionPayload } from '../validation.js';
import type { SubscriptionData, SignedSubscriptionBlob } from '../types.js';

// Fixed test keys for deterministic tests (from account-server test helpers)
const TEST_PUBLIC_KEY_SPKI = 'MCowBQYDK2VwAyEAqS7xKEfPYFtCWxOCRUvKG5N6peFHSAYBNMJqGRMHN5I=';
const TEST_PRIVATE_KEY_PKCS8 = 'MC4CAQAwBQYDK2VwBCIEIBXIuPTQjPy6a4X2qbLBwF3VDj7yMqJ4kGzJu8vKMKqd';
const TEST_KEY_ID = 'test-key-2026';

const createValidSubscriptionData = (
  overrides: Partial<SubscriptionData> = {}
): SubscriptionData => ({
  version: 1,
  subscriptionId: 'test-subscription-id',
  organizationId: 1,
  customerId: 'test-customer',
  planCode: 'PROFESSIONAL',
  status: 'ACTIVE',
  issuedAt: '2026-01-01T00:00:00Z',
  expiresAt: '2027-01-01T00:00:00Z',
  lastCheckIn: new Date().toISOString(),
  gracePeriodEnds: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(),
  resources: PLAN_RESOURCES.PROFESSIONAL,
  features: PLAN_FEATURES.PROFESSIONAL,
  maxActivations: 5,
  activationCount: 1,
  ...overrides,
});

describe('Subscription Crypto', () => {
  afterEach(() => {
    clearPublicKeys();
  });

  describe('Key Management', () => {
    describe('importPublicKey', () => {
      it('should import a valid SPKI Ed25519 public key', async () => {
        await importPublicKey(TEST_KEY_ID, TEST_PUBLIC_KEY_SPKI);
        expect(hasPublicKey(TEST_KEY_ID)).toBe(true);
      });

      it('should import a dynamically generated public key', async () => {
        const { publicKey } = await generateKeyPair();
        await importPublicKey('dynamic-key', publicKey);
        expect(hasPublicKey('dynamic-key')).toBe(true);
      });

      it('should reject invalid base64 key data', async () => {
        await expect(importPublicKey('bad-key', '!!!not-base64!!!')).rejects.toThrow();
      });

      it('should support multiple key registrations', async () => {
        const pair1 = await generateKeyPair();
        const pair2 = await generateKeyPair();
        await importPublicKey('key-1', pair1.publicKey);
        await importPublicKey('key-2', pair2.publicKey);
        expect(getPublicKeyIds()).toHaveLength(2);
        expect(hasPublicKey('key-1')).toBe(true);
        expect(hasPublicKey('key-2')).toBe(true);
      });

      it('should overwrite a key with the same ID', async () => {
        const pair1 = await generateKeyPair();
        const pair2 = await generateKeyPair();
        await importPublicKey('same-id', pair1.publicKey);
        await importPublicKey('same-id', pair2.publicKey);
        expect(getPublicKeyIds()).toHaveLength(1);
      });
    });

    describe('hasPublicKey', () => {
      it('should return false for unregistered key ID', () => {
        expect(hasPublicKey('nonexistent')).toBe(false);
      });

      it('should return true after key import', async () => {
        await importPublicKey(TEST_KEY_ID, TEST_PUBLIC_KEY_SPKI);
        expect(hasPublicKey(TEST_KEY_ID)).toBe(true);
      });
    });

    describe('getPublicKeyIds', () => {
      it('should return empty array when no keys registered', () => {
        expect(getPublicKeyIds()).toEqual([]);
      });

      it('should return all registered key IDs', async () => {
        const pair1 = await generateKeyPair();
        const pair2 = await generateKeyPair();
        const pair3 = await generateKeyPair();
        await importPublicKey('a', pair1.publicKey);
        await importPublicKey('b', pair2.publicKey);
        await importPublicKey('c', pair3.publicKey);
        const ids = getPublicKeyIds();
        expect(ids).toHaveLength(3);
        expect(ids).toContain('a');
        expect(ids).toContain('b');
        expect(ids).toContain('c');
      });
    });

    describe('clearPublicKeys', () => {
      it('should remove all registered keys', async () => {
        const pair1 = await generateKeyPair();
        const pair2 = await generateKeyPair();
        await importPublicKey('key-1', pair1.publicKey);
        await importPublicKey('key-2', pair2.publicKey);
        expect(getPublicKeyIds()).toHaveLength(2);
        clearPublicKeys();
        expect(getPublicKeyIds()).toEqual([]);
        expect(hasPublicKey('key-1')).toBe(false);
      });
    });
  });

  describe('Key Generation and Import', () => {
    describe('generateKeyPair', () => {
      it('should generate base64-encoded public and private keys', async () => {
        const { publicKey, privateKey } = await generateKeyPair();
        expect(typeof publicKey).toBe('string');
        expect(typeof privateKey).toBe('string');
        expect(publicKey.length).toBeGreaterThan(0);
        expect(privateKey.length).toBeGreaterThan(0);
      });

      it('should generate unique key pairs on each call', async () => {
        const pair1 = await generateKeyPair();
        const pair2 = await generateKeyPair();
        expect(pair1.publicKey).not.toBe(pair2.publicKey);
        expect(pair1.privateKey).not.toBe(pair2.privateKey);
      });

      it('should generate keys usable by importPublicKey and importPrivateKey', async () => {
        const { publicKey, privateKey } = await generateKeyPair();
        await expect(importPublicKey('gen-key', publicKey)).resolves.not.toThrow();
        await expect(importPrivateKey(privateKey)).resolves.not.toThrow();
      });
    });

    describe('importPrivateKey', () => {
      it('should import a valid PKCS8 private key', async () => {
        const key = await importPrivateKey(TEST_PRIVATE_KEY_PKCS8);
        expect(key).toBeDefined();
        expect(key.type).toBe('private');
      });

      it('should reject invalid key data', async () => {
        await expect(importPrivateKey('!!!not-a-key!!!')).rejects.toThrow();
      });
    });
  });

  describe('Signing', () => {
    describe('signSubscriptionPayload', () => {
      it('should produce a valid SignedSubscriptionBlob structure', async () => {
        const privateKey = await importPrivateKey(TEST_PRIVATE_KEY_PKCS8);
        const payload = encodeSubscriptionPayload(createValidSubscriptionData());
        const blob = await signSubscriptionPayload(payload, privateKey, TEST_KEY_ID);

        expect(blob).toHaveProperty('payload');
        expect(blob).toHaveProperty('signature');
        expect(blob).toHaveProperty('publicKeyId');
        expect(blob.publicKeyId).toBe(TEST_KEY_ID);
      });

      it('should preserve the original payload in the blob', async () => {
        const privateKey = await importPrivateKey(TEST_PRIVATE_KEY_PKCS8);
        const payload = encodeSubscriptionPayload(createValidSubscriptionData());
        const blob = await signSubscriptionPayload(payload, privateKey, TEST_KEY_ID);

        expect(blob.payload).toBe(payload);
      });

      it('should produce different signatures for different payloads', async () => {
        const privateKey = await importPrivateKey(TEST_PRIVATE_KEY_PKCS8);
        const payload1 = encodeSubscriptionPayload(
          createValidSubscriptionData({ subscriptionId: 'sub-1' })
        );
        const payload2 = encodeSubscriptionPayload(
          createValidSubscriptionData({ subscriptionId: 'sub-2' })
        );
        const blob1 = await signSubscriptionPayload(payload1, privateKey, TEST_KEY_ID);
        const blob2 = await signSubscriptionPayload(payload2, privateKey, TEST_KEY_ID);

        expect(blob1.signature).not.toBe(blob2.signature);
      });
    });

    describe('createSignedSubscription', () => {
      it('should create a signed subscription blob from SubscriptionData', async () => {
        const privateKey = await importPrivateKey(TEST_PRIVATE_KEY_PKCS8);
        const data = createValidSubscriptionData();
        const blob = await createSignedSubscription(data, privateKey, TEST_KEY_ID);

        expect(blob.payload).toBeDefined();
        expect(blob.signature).toBeDefined();
        expect(blob.publicKeyId).toBe(TEST_KEY_ID);
      });

      it('should encode subscription data as base64 JSON in payload', async () => {
        const privateKey = await importPrivateKey(TEST_PRIVATE_KEY_PKCS8);
        const data = createValidSubscriptionData();
        const blob = await createSignedSubscription(data, privateKey, TEST_KEY_ID);

        const decoded = JSON.parse(atob(blob.payload));
        expect(decoded.subscriptionId).toBe(data.subscriptionId);
        expect(decoded.planCode).toBe(data.planCode);
      });

      it('should create verifiable signed subscriptions', async () => {
        const { publicKey, privateKey: privKeyBase64 } = await generateKeyPair();
        const privateKey = await importPrivateKey(privKeyBase64);
        await importPublicKey('round-trip-key', publicKey);

        const data = createValidSubscriptionData();
        const blob = await createSignedSubscription(data, privateKey, 'round-trip-key');

        const isValid = await verifySignature(blob);
        expect(isValid).toBe(true);
      });
    });
  });

  describe('Verification', () => {
    describe('verifySignature', () => {
      it('should return true for a valid signature', async () => {
        const { publicKey, privateKey: privKeyBase64 } = await generateKeyPair();
        const privateKey = await importPrivateKey(privKeyBase64);
        await importPublicKey('verify-key', publicKey);

        const data = createValidSubscriptionData();
        const blob = await createSignedSubscription(data, privateKey, 'verify-key');

        expect(await verifySignature(blob)).toBe(true);
      });

      it('should return false for tampered payload', async () => {
        const { publicKey, privateKey: privKeyBase64 } = await generateKeyPair();
        const privateKey = await importPrivateKey(privKeyBase64);
        await importPublicKey('verify-key', publicKey);

        const data = createValidSubscriptionData();
        const blob = await createSignedSubscription(data, privateKey, 'verify-key');

        const tampered: SignedSubscriptionBlob = {
          ...blob,
          payload: encodeSubscriptionPayload(
            createValidSubscriptionData({ subscriptionId: 'tampered' })
          ),
        };

        expect(await verifySignature(tampered)).toBe(false);
      });

      it('should return false for tampered signature', async () => {
        const { publicKey, privateKey: privKeyBase64 } = await generateKeyPair();
        const privateKey = await importPrivateKey(privKeyBase64);
        await importPublicKey('verify-key', publicKey);

        const data = createValidSubscriptionData();
        const blob = await createSignedSubscription(data, privateKey, 'verify-key');

        const tampered: SignedSubscriptionBlob = {
          ...blob,
          signature: `AAAA${blob.signature.slice(4)}`,
        };

        expect(await verifySignature(tampered)).toBe(false);
      });

      it('should return false for unknown publicKeyId', async () => {
        const { privateKey: privKeyBase64 } = await generateKeyPair();
        const privateKey = await importPrivateKey(privKeyBase64);
        // Deliberately not importing the public key

        const data = createValidSubscriptionData();
        const blob = await createSignedSubscription(data, privateKey, 'unknown-key');

        expect(await verifySignature(blob)).toBe(false);
      });

      it('should return false when no keys are registered', async () => {
        const blob: SignedSubscriptionBlob = {
          payload: encodeSubscriptionPayload(createValidSubscriptionData()),
          signature: 'dGVzdC1zaWduYXR1cmU=',
          publicKeyId: 'any-key',
        };

        expect(await verifySignature(blob)).toBe(false);
      });

      it('should reject signature from wrong key pair', async () => {
        const pairA = await generateKeyPair();
        const pairB = await generateKeyPair();

        // Sign with key A
        const privateKeyA = await importPrivateKey(pairA.privateKey);
        const data = createValidSubscriptionData();
        const blob = await createSignedSubscription(data, privateKeyA, 'key-b');

        // Register key B's public key under the same ID
        await importPublicKey('key-b', pairB.publicKey);

        expect(await verifySignature(blob)).toBe(false);
      });
    });

    describe('verifyAndDecodeSubscription', () => {
      it('should verify, decode, and validate a valid subscription', async () => {
        const { publicKey, privateKey: privKeyBase64 } = await generateKeyPair();
        const privateKey = await importPrivateKey(privKeyBase64);
        await importPublicKey('decode-key', publicKey);

        const data = createValidSubscriptionData();
        const blob = await createSignedSubscription(data, privateKey, 'decode-key');

        const result = await verifyAndDecodeSubscription(blob);
        expect(result.valid).toBe(true);
        expect(result.data).toBeDefined();
        expect(result.data?.subscriptionId).toBe('test-subscription-id');
        expect(result.data?.planCode).toBe('PROFESSIONAL');
      });

      it('should return invalid signature error for tampered blob', async () => {
        const { publicKey, privateKey: privKeyBase64 } = await generateKeyPair();
        const privateKey = await importPrivateKey(privKeyBase64);
        await importPublicKey('verify-key', publicKey);

        const data = createValidSubscriptionData();
        const blob = await createSignedSubscription(data, privateKey, 'verify-key');

        const tampered: SignedSubscriptionBlob = {
          ...blob,
          signature: `AAAA${blob.signature.slice(4)}`,
        };

        const result = await verifyAndDecodeSubscription(tampered);
        expect(result.valid).toBe(false);
        expect(result.error).toContain('Invalid signature');
      });

      it('should return invalid payload error for non-JSON payload', async () => {
        const { publicKey, privateKey: privKeyBase64 } = await generateKeyPair();
        const privateKey = await importPrivateKey(privKeyBase64);
        await importPublicKey('payload-key', publicKey);

        // Sign a payload that is valid base64 but not valid subscription JSON
        const payload = btoa('not-json-data');
        const blob = await signSubscriptionPayload(payload, privateKey, 'payload-key');

        const result = await verifyAndDecodeSubscription(blob);
        expect(result.valid).toBe(false);
        expect(result.error).toContain('Invalid subscription payload');
      });

      it('should propagate validation result for expired subscription', async () => {
        const { publicKey, privateKey: privKeyBase64 } = await generateKeyPair();
        const privateKey = await importPrivateKey(privKeyBase64);
        await importPublicKey('expired-key', publicKey);

        const data = createValidSubscriptionData({
          expiresAt: '2020-01-01T00:00:00Z',
        });
        const blob = await createSignedSubscription(data, privateKey, 'expired-key');

        const result = await verifyAndDecodeSubscription(blob);
        expect(result.valid).toBe(false);
        expect(result.error).toContain('expired');
      });
    });
  });

  // Cross-language fixture verification (requires account submodule)
  const FIXTURES_PATH = resolve(
    __dirname,
    '../../../../../private/account/tests/integration/cross-language/fixtures.json'
  );
  describe.skipIf(!existsSync(FIXTURES_PATH))('Cross-Language Fixture Verification', () => {
    interface Fixture {
      name: string;
      signedBlob: SignedSubscriptionBlob;
      expectedValid: boolean;
    }

    interface FixturesFile {
      publicKey: { spki: string };
      keyId: string;
      fixtures: Fixture[];
    }

    let fixtures: FixturesFile;

    function getFixture(name: string): Fixture {
      const fixture = fixtures.fixtures.find((f) => f.name === name);
      if (!fixture) throw new Error(`Fixture ${name} not found`);
      return fixture;
    }

    beforeAll(async () => {
      fixtures = JSON.parse(readFileSync(FIXTURES_PATH, 'utf-8'));
      await importPublicKey(fixtures.keyId, fixtures.publicKey.spki);
    });

    it('should verify valid_business_license fixture signature', async () => {
      const fixture = getFixture('valid_business_license');
      const isValid = await verifySignature(fixture.signedBlob);
      expect(isValid).toBe(true);
    });

    it('should reject tampered_signature fixture', async () => {
      const fixture = getFixture('tampered_signature');
      const isValid = await verifySignature(fixture.signedBlob);
      expect(isValid).toBe(false);
    });
  });
});
