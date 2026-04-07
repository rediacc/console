import { describe, expect, it } from 'vitest';
import {
  canonicalManifestBytes,
  isManifestExpired,
  RENEWAL_MANIFEST_MAX_AGE_MS,
  RENEWAL_MANIFEST_SCHEMA_VERSION,
  type RenewalRequestManifest,
  type SignedRenewalRequestManifest,
  verifyManifestSignature,
} from '../index';

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

const NOW = new Date('2026-04-15T12:00:00.000Z');

function makeManifest(overrides: Partial<RenewalRequestManifest> = {}): RenewalRequestManifest {
  return {
    schemaVersion: RENEWAL_MANIFEST_SCHEMA_VERSION,
    generatedAt: NOW.toISOString(),
    subscriptionId: 'sub-test',
    currentChainHash: 'abc123',
    currentSequence: 42,
    delegatedPublicKey: 'placeholder', // overridden in signature tests
    currentCertValidUntil: new Date(NOW.getTime() + 30 * 86_400_000).toISOString(),
    currentCertPublicKeyId: 'cert-key-1',
    currentCertId: 'local-row-id',
    ...overrides,
  };
}

describe('canonicalManifestBytes', () => {
  it('produces deterministic output regardless of property insertion order', () => {
    const a = makeManifest();
    // Reconstruct in different key order
    const b: RenewalRequestManifest = {
      currentSequence: a.currentSequence,
      delegatedPublicKey: a.delegatedPublicKey,
      schemaVersion: a.schemaVersion,
      subscriptionId: a.subscriptionId,
      currentChainHash: a.currentChainHash,
      generatedAt: a.generatedAt,
      currentCertValidUntil: a.currentCertValidUntil,
      currentCertPublicKeyId: a.currentCertPublicKeyId,
      currentCertId: a.currentCertId,
    };
    const bytesA = canonicalManifestBytes(a);
    const bytesB = canonicalManifestBytes(b);
    expect(Array.from(bytesA)).toEqual(Array.from(bytesB));
  });

  it('produces different bytes when a field changes', () => {
    const a = makeManifest();
    const b = makeManifest({ currentSequence: 43 });
    const bytesA = canonicalManifestBytes(a);
    const bytesB = canonicalManifestBytes(b);
    expect(Array.from(bytesA)).not.toEqual(Array.from(bytesB));
  });
});

describe('verifyManifestSignature', () => {
  let keyPair: CryptoKeyPair;
  let publicKeySpki: string;
  let otherPublicKeySpki: string;

  beforeAll(async () => {
    keyPair = await crypto.subtle.generateKey('Ed25519', true, ['sign', 'verify']);
    const spki = await crypto.subtle.exportKey('spki', keyPair.publicKey);
    publicKeySpki = bytesToBase64(new Uint8Array(spki));

    // Generate a separate keypair for the "different key" test.
    const other = await crypto.subtle.generateKey('Ed25519', true, ['sign', 'verify']);
    const otherSpki = await crypto.subtle.exportKey('spki', other.publicKey);
    otherPublicKeySpki = bytesToBase64(new Uint8Array(otherSpki));
  });

  async function signManifest(
    manifest: RenewalRequestManifest
  ): Promise<SignedRenewalRequestManifest> {
    const bytes = canonicalManifestBytes(manifest);
    const sig = await crypto.subtle.sign(
      'Ed25519',
      keyPair.privateKey,
      bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
    );
    return {
      manifest,
      signature: bytesToBase64(new Uint8Array(sig)),
      publicKeyId: 'test-key',
    };
  }

  it('accepts a manifest signed with the matching key', async () => {
    const signed = await signManifest(makeManifest({ delegatedPublicKey: publicKeySpki }));
    const valid = await verifyManifestSignature(signed, publicKeySpki);
    expect(valid).toBe(true);
  });

  it('rejects a manifest with tampered fields', async () => {
    const signed = await signManifest(makeManifest({ delegatedPublicKey: publicKeySpki }));
    // Tamper with the manifest after signing
    const tampered: SignedRenewalRequestManifest = {
      ...signed,
      manifest: { ...signed.manifest, currentSequence: 999 },
    };
    const valid = await verifyManifestSignature(tampered, publicKeySpki);
    expect(valid).toBe(false);
  });

  it('rejects a manifest signed with a different key', async () => {
    const signed = await signManifest(makeManifest({ delegatedPublicKey: publicKeySpki }));
    const valid = await verifyManifestSignature(signed, otherPublicKeySpki);
    expect(valid).toBe(false);
  });

  it('rejects a manifest with malformed signature bytes', async () => {
    const signed: SignedRenewalRequestManifest = {
      manifest: makeManifest({ delegatedPublicKey: publicKeySpki }),
      signature: 'not-valid-base64-!!!',
      publicKeyId: 'test-key',
    };
    const valid = await verifyManifestSignature(signed, publicKeySpki);
    expect(valid).toBe(false);
  });

  it('rejects a manifest with malformed public key', async () => {
    const signed = await signManifest(makeManifest({ delegatedPublicKey: publicKeySpki }));
    const valid = await verifyManifestSignature(signed, 'not-a-spki-key');
    expect(valid).toBe(false);
  });
});

describe('isManifestExpired', () => {
  it('returns false for a fresh manifest', () => {
    const m = makeManifest({ generatedAt: NOW.toISOString() });
    expect(isManifestExpired(m, NOW)).toBe(false);
  });

  it('returns false for a manifest 6 days old (under 7-day cutoff)', () => {
    const m = makeManifest({ generatedAt: new Date(NOW.getTime() - 6 * 86_400_000).toISOString() });
    expect(isManifestExpired(m, NOW)).toBe(false);
  });

  it('returns true for a manifest 8 days old', () => {
    const m = makeManifest({ generatedAt: new Date(NOW.getTime() - 8 * 86_400_000).toISOString() });
    expect(isManifestExpired(m, NOW)).toBe(true);
  });

  it('uses the configured 7-day cutoff', () => {
    expect(RENEWAL_MANIFEST_MAX_AGE_MS).toBe(7 * 24 * 60 * 60 * 1000);
  });
});

// Vitest's beforeAll is imported automatically via the global describe context.
// We need to import it explicitly because we're defining it at the top.
import { beforeAll } from 'vitest';
