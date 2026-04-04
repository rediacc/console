import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  clearPublicKeys,
  importPrivateKey,
  importPublicKey,
  signSubscriptionPayload,
  verifySignature,
} from '../../subscription/crypto.js';
import type { SignedSubscriptionBlob } from '../../subscription/types.js';
import { BAKED_IN_REGIONS, DEFAULT_REGION, verifySignedRegions, type RegionInfo } from '../index.js';

// Test keys (same as subscription crypto tests)
// Fresh Ed25519 key pair generated for tests (verified to work with Node 22 crypto.subtle)
const TEST_PUBLIC_KEY_SPKI = 'MCowBQYDK2VwAyEAFKKPwa2eTAOh+Ho3ntplPtbvHN90DywcbrjJx0+C27c=';
const TEST_PRIVATE_KEY_PKCS8 = 'MC4CAQAwBQYDK2VwBCIEIKGh5gpzYDqjKcH0DIml3uFrKyFR3Tv7j02Z1nT4MXAA';
const TEST_KEY_ID = 'test-key-regions';

// Mock signing-keys so verifySignedRegions uses our test key
vi.mock('../../subscription/signing-keys.js', () => ({
  SIGNING_KEYS: [
    {
      keyId: 'test-key-regions',
      publicKeySpki: 'MCowBQYDK2VwAyEAFKKPwa2eTAOh+Ho3ntplPtbvHN90DywcbrjJx0+C27c=',
    },
  ],
  CURRENT_SIGNING_KEY: {
    keyId: 'test-key-regions',
    publicKeySpki: 'MCowBQYDK2VwAyEAFKKPwa2eTAOh+Ho3ntplPtbvHN90DywcbrjJx0+C27c=',
  },
}));

const TEST_REGIONS: RegionInfo[] = [
  { id: 'eu', label: 'Europe', domain: 'eu.rediacc.com', default: true },
  { id: 'us', label: 'United States', domain: 'us.rediacc.com', default: false },
];

async function signPayload(payload: string): Promise<SignedSubscriptionBlob> {
  const privateKey = await importPrivateKey(TEST_PRIVATE_KEY_PKCS8);
  return signSubscriptionPayload(payload, privateKey, TEST_KEY_ID);
}

describe('Regions', () => {
  afterEach(() => {
    clearPublicKeys();
  });

  describe('BAKED_IN_REGIONS', () => {
    it('should be a non-empty array', () => {
      expect(Array.isArray(BAKED_IN_REGIONS)).toBe(true);
      expect(BAKED_IN_REGIONS.length).toBeGreaterThan(0);
    });

    it('should have correct shape for each region', () => {
      for (const region of BAKED_IN_REGIONS) {
        expect(region).toHaveProperty('id');
        expect(region).toHaveProperty('label');
        expect(region).toHaveProperty('domain');
        expect(typeof region.default).toBe('boolean');
      }
    });
  });

  describe('DEFAULT_REGION', () => {
    it('should have default: true', () => {
      expect(DEFAULT_REGION.default).toBe(true);
    });

    it('should be one of the baked-in regions', () => {
      expect(BAKED_IN_REGIONS.some((r) => r.id === DEFAULT_REGION.id)).toBe(true);
    });
  });

  describe('verifySignedRegions', () => {
    it('should return regions for a valid signed blob', async () => {
      const payload = JSON.stringify(TEST_REGIONS);
      const blob = await signPayload(payload);

      const result = await verifySignedRegions(blob);
      expect(result).toEqual(TEST_REGIONS);
    });

    it('should return null for invalid signature', async () => {
      const payload = JSON.stringify(TEST_REGIONS);
      const blob = await signPayload(payload);

      const tampered: SignedSubscriptionBlob = {
        ...blob,
        signature: blob.signature.replace(/^./, 'X'),
      };
      const result = await verifySignedRegions(tampered);
      expect(result).toBeNull();
    });

    it('should return null for tampered payload', async () => {
      const payload = JSON.stringify(TEST_REGIONS);
      const blob = await signPayload(payload);

      const tampered: SignedSubscriptionBlob = {
        ...blob,
        payload: JSON.stringify([{ id: 'evil', label: 'Evil', domain: 'evil.com', default: true }]),
      };
      const result = await verifySignedRegions(tampered);
      expect(result).toBeNull();
    });

    it('should return null for unknown publicKeyId', async () => {
      const payload = JSON.stringify(TEST_REGIONS);
      const blob = await signPayload(payload);

      const unknown: SignedSubscriptionBlob = {
        ...blob,
        publicKeyId: 'unknown-key-id',
      };
      const result = await verifySignedRegions(unknown);
      expect(result).toBeNull();
    });

    it('should return null for malformed JSON payload', async () => {
      const blob = await signPayload('not valid json {{{');
      const result = await verifySignedRegions(blob);
      expect(result).toBeNull();
    });

    it('should return null for empty regions array', async () => {
      const blob = await signPayload('[]');
      const result = await verifySignedRegions(blob);
      expect(result).toBeNull();
    });

    it('should verify directly with crypto module', async () => {
      // Sanity check: verify the test keys work with the underlying crypto
      await importPublicKey(TEST_KEY_ID, TEST_PUBLIC_KEY_SPKI);
      const payload = 'test payload';
      const blob = await signPayload(payload);
      const valid = await verifySignature(blob);
      expect(valid).toBe(true);
    });
  });
});
