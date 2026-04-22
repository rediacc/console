/**
 * Integration Tests — Full Config Storage Encryption Lifecycle
 *
 * Tests the complete triple-layer encryption chain:
 * plaintext → sdk_derived → CEK → orgPassphrase → stored
 * stored → orgPassphrase → CEK → sdk_derived → plaintext
 */

import { describe, expect, it } from 'vitest';
import {
  cekHandoffDecrypt,
  cekHandoffEncrypt,
  cekUnwrap,
  cekWrap,
  configDecrypt,
  configEncrypt,
  deriveWrappingKey,
  exportAesKey,
  generateAesKey,
  generateCek,
  generateSdkMaster,
  generateServerSecret,
  hmacCompute,
  hmacVerify,
  importAesKey,
  orgDecrypt,
  orgEncrypt,
  randomBytes,
  sdkDerive,
  sdkGetEpoch,
  selectiveDecrypt,
  selectiveEncrypt,
  toBase64,
} from '../index.js';
import type { FullConfig } from '../types.js';

// ─── AES-256-GCM ────────────────────────────────────────────────────────────

describe('AES-256-GCM', () => {
  it('encrypts and decrypts round-trip', async () => {
    const key = await generateAesKey();
    const plaintext = new TextEncoder().encode('hello world');
    const { iv, ct } = await (await import('../aes.js')).aesEncrypt(key, plaintext);
    const decrypted = await (await import('../aes.js')).aesDecrypt(key, iv, ct);
    expect(new TextDecoder().decode(decrypted)).toBe('hello world');
  });

  it('decrypt with wrong key throws', async () => {
    const key1 = await generateAesKey();
    const key2 = await generateAesKey();
    const plaintext = new TextEncoder().encode('secret');
    const { iv, ct } = await (await import('../aes.js')).aesEncrypt(key1, plaintext);
    await expect((await import('../aes.js')).aesDecrypt(key2, iv, ct)).rejects.toThrow();
  });

  it('tamper detection — flipped bit in ciphertext', async () => {
    const key = await generateAesKey();
    const plaintext = new TextEncoder().encode('tamper test');
    const { iv, ct } = await (await import('../aes.js')).aesEncrypt(key, plaintext);
    ct[0] ^= 0xff; // flip bits
    await expect((await import('../aes.js')).aesDecrypt(key, iv, ct)).rejects.toThrow();
  });

  it('handles empty plaintext', async () => {
    const key = await generateAesKey();
    const plaintext = new Uint8Array(0);
    const { iv, ct } = await (await import('../aes.js')).aesEncrypt(key, plaintext);
    const decrypted = await (await import('../aes.js')).aesDecrypt(key, iv, ct);
    expect(decrypted.byteLength).toBe(0);
  });

  it('unique IV per encryption', async () => {
    const key = await generateAesKey();
    const plaintext = new TextEncoder().encode('same input');
    const r1 = await (await import('../aes.js')).aesEncrypt(key, plaintext);
    const r2 = await (await import('../aes.js')).aesEncrypt(key, plaintext);
    expect(toBase64(r1.iv)).not.toBe(toBase64(r2.iv));
    expect(toBase64(r1.ct)).not.toBe(toBase64(r2.ct));
  });

  it('string encrypt/decrypt round-trip', async () => {
    const key = await generateAesKey();
    const plaintext = new TextEncoder().encode('string round-trip');
    const { aesEncryptToString, aesDecryptFromString } = await import('../aes.js');
    const encrypted = await aesEncryptToString(key, plaintext);
    const decrypted = await aesDecryptFromString(key, encrypted);
    expect(new TextDecoder().decode(decrypted)).toBe('string round-trip');
  });
});

// ─── HKDF ────────────────────────────────────────────────────────────────────

describe('HKDF', () => {
  it('deterministic — same inputs produce same output', async () => {
    const { hkdfDeriveRaw } = await import('../hkdf.js');
    const ikm = randomBytes(32);
    const salt = randomBytes(16);
    const r1 = await hkdfDeriveRaw(ikm, salt, 'test-info');
    const r2 = await hkdfDeriveRaw(ikm, salt, 'test-info');
    expect(toBase64(r1)).toBe(toBase64(r2));
  });

  it('different salt produces different output', async () => {
    const { hkdfDeriveRaw } = await import('../hkdf.js');
    const ikm = randomBytes(32);
    const r1 = await hkdfDeriveRaw(ikm, randomBytes(16), 'test-info');
    const r2 = await hkdfDeriveRaw(ikm, randomBytes(16), 'test-info');
    expect(toBase64(r1)).not.toBe(toBase64(r2));
  });

  it('different info produces different output', async () => {
    const { hkdfDeriveRaw } = await import('../hkdf.js');
    const ikm = randomBytes(32);
    const salt = randomBytes(16);
    const r1 = await hkdfDeriveRaw(ikm, salt, 'info-a');
    const r2 = await hkdfDeriveRaw(ikm, salt, 'info-b');
    expect(toBase64(r1)).not.toBe(toBase64(r2));
  });

  it('output is 32 bytes (256 bits)', async () => {
    const { hkdfDeriveRaw } = await import('../hkdf.js');
    const result = await hkdfDeriveRaw(randomBytes(32), randomBytes(16), 'test');
    expect(result.byteLength).toBe(32);
  });
});

// ─── SDK Derivation ──────────────────────────────────────────────────────────

describe('SDK', () => {
  it('same master + same epoch → same derived key', async () => {
    const master = generateSdkMaster();
    const epoch = 5913166;
    const k1 = await sdkDerive(master, epoch);
    const k2 = await sdkDerive(master, epoch);
    const raw1 = await exportAesKey(k1);
    const raw2 = await exportAesKey(k2);
    expect(toBase64(raw1)).toBe(toBase64(raw2));
  });

  it('same master + different epoch → different derived key', async () => {
    const master = generateSdkMaster();
    const k1 = await sdkDerive(master, 5913166);
    const k2 = await sdkDerive(master, 5913167);
    const raw1 = await exportAesKey(k1);
    const raw2 = await exportAesKey(k2);
    expect(toBase64(raw1)).not.toBe(toBase64(raw2));
  });

  it('sdkGetEpoch returns consistent values within same window', () => {
    // Use a fixed mid-window timestamp, not wall-clock, so the test can't
    // straddle a window boundary when CI hits (now mod 300) === 299.
    const windowStart = 300 * 5_000_000;
    const e1 = sdkGetEpoch(300, windowStart + 50);
    const e2 = sdkGetEpoch(300, windowStart + 51);
    expect(e1).toBe(e2);
  });

  it('sdkGetEpoch changes at window boundary', () => {
    const e1 = sdkGetEpoch(300, 300);
    const e2 = sdkGetEpoch(300, 599);
    const e3 = sdkGetEpoch(300, 600);
    expect(e1).toBe(e2); // same window
    expect(e2).not.toBe(e3); // different window
  });
});

// ─── CEK Wrap/Unwrap ─────────────────────────────────────────────────────────

describe('CEK', () => {
  it('wrap/unwrap round-trip', async () => {
    const cek = await generateCek();
    const passkeySecret = randomBytes(32);
    const serverSecret = generateServerSecret();
    const wrappingKey = await deriveWrappingKey(passkeySecret, serverSecret);

    const wrapped = await cekWrap(cek, wrappingKey);
    const unwrapped = await cekUnwrap(wrapped, wrappingKey);

    const cekRaw = await exportAesKey(cek);
    const unwrappedRaw = await exportAesKey(unwrapped);
    expect(toBase64(cekRaw)).toBe(toBase64(unwrappedRaw));
  });

  it('unwrap with wrong key throws', async () => {
    const cek = await generateCek();
    const wrappingKey1 = await deriveWrappingKey(randomBytes(32), randomBytes(32));
    const wrappingKey2 = await deriveWrappingKey(randomBytes(32), randomBytes(32));

    const wrapped = await cekWrap(cek, wrappingKey1);
    await expect(cekUnwrap(wrapped, wrappingKey2)).rejects.toThrow();
  });

  it('different wrapping keys produce different wrapped CEK', async () => {
    const cek = await generateCek();
    const wk1 = await deriveWrappingKey(randomBytes(32), randomBytes(32));
    const wk2 = await deriveWrappingKey(randomBytes(32), randomBytes(32));

    const wrapped1 = await cekWrap(cek, wk1);
    const wrapped2 = await cekWrap(cek, wk2);
    expect(wrapped1).not.toBe(wrapped2);
  });
});

// ─── Triple-Layer Encryption ─────────────────────────────────────────────────

describe('Layers', () => {
  it('configEncrypt → configDecrypt round-trip', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();
    const plaintext = JSON.stringify({ machines: { server1: { ip: '10.0.0.1' } } });

    const encrypted = await configEncrypt(plaintext, sdkKey, cek);
    const decrypted = await configDecrypt(encrypted, cek, sdkKey);
    expect(decrypted).toBe(plaintext);
  });

  it('configDecrypt with wrong CEK throws', async () => {
    const sdkKey = await generateAesKey();
    const cek1 = await generateCek();
    const cek2 = await generateCek();

    const encrypted = await configEncrypt('secret', sdkKey, cek1);
    await expect(configDecrypt(encrypted, cek2, sdkKey)).rejects.toThrow();
  });

  it('configDecrypt with wrong SDK throws', async () => {
    const sdk1 = await generateAesKey();
    const sdk2 = await generateAesKey();
    const cek = await generateCek();

    const encrypted = await configEncrypt('secret', sdk1, cek);
    await expect(configDecrypt(encrypted, cek, sdk2)).rejects.toThrow();
  });

  it('orgEncrypt → orgDecrypt round-trip', async () => {
    const orgPassphrase = randomBytes(32);
    const data = 'client-encrypted-blob-here';

    const encrypted = await orgEncrypt(data, orgPassphrase);
    const decrypted = await orgDecrypt(encrypted, orgPassphrase);
    expect(decrypted).toBe(data);
  });

  it('full triple layer round-trip', async () => {
    const sdkMaster = generateSdkMaster();
    const epoch = sdkGetEpoch();
    const sdkKey = await sdkDerive(sdkMaster, epoch);
    const cek = await generateCek();
    const orgPassphrase = randomBytes(32);

    const plaintext = JSON.stringify({ ssh: { key: 'private-key-data' } });

    // CLI side: Layer 1 (SDK) + Layer 2 (CEK)
    const clientEncrypted = await configEncrypt(plaintext, sdkKey, cek);

    // Server side: Layer 3 (Org)
    const stored = await orgEncrypt(clientEncrypted, orgPassphrase);

    // Server side: Remove Layer 3
    const afterOrg = await orgDecrypt(stored, orgPassphrase);

    // CLI side: Remove Layer 2 + Layer 1
    const result = await configDecrypt(afterOrg, cek, sdkKey);
    expect(result).toBe(plaintext);
  });
});

// ─── HMAC ────────────────────────────────────────────────────────────────────

describe('HMAC', () => {
  it('compute + verify round-trip', async () => {
    const cek = await generateCek();
    const data = 'encrypted-blob-base64-data';

    const hmac = await hmacCompute(data, cek);
    const valid = await hmacVerify(data, cek, hmac);
    expect(valid).toBe(true);
  });

  it('tampered data fails verification', async () => {
    const cek = await generateCek();
    const hmac = await hmacCompute('original', cek);
    const valid = await hmacVerify('tampered', cek, hmac);
    expect(valid).toBe(false);
  });

  it('different CEK produces different HMAC', async () => {
    const cek1 = await generateCek();
    const cek2 = await generateCek();
    const data = 'same-data';

    const hmac1 = await hmacCompute(data, cek1);
    const hmac2 = await hmacCompute(data, cek2);
    expect(hmac1).not.toBe(hmac2);
  });
});

// ─── X25519 Handoff ──────────────────────────────────────────────────────────

describe('CEK Handoff', () => {
  it('encrypt → decrypt round-trip', async () => {
    // Recipient generates X25519 key pair
    const recipientKeyPair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, [
      'deriveBits',
    ])) as unknown as { publicKey: CryptoKey; privateKey: CryptoKey };

    const cek = await generateCek();
    const cekRaw = await exportAesKey(cek);

    // Admin encrypts CEK for recipient
    const blob = await cekHandoffEncrypt(cekRaw, recipientKeyPair.publicKey);

    // Recipient decrypts
    const decryptedCek = await cekHandoffDecrypt(blob, recipientKeyPair.privateKey);
    expect(toBase64(decryptedCek)).toBe(toBase64(cekRaw));
  });

  it('decrypt with wrong private key throws', async () => {
    const recipientKeyPair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, [
      'deriveBits',
    ])) as unknown as { publicKey: CryptoKey; privateKey: CryptoKey };
    const wrongKeyPair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, [
      'deriveBits',
    ])) as unknown as { publicKey: CryptoKey; privateKey: CryptoKey };

    const cekRaw = randomBytes(32);
    const blob = await cekHandoffEncrypt(cekRaw, recipientKeyPair.publicKey);
    await expect(cekHandoffDecrypt(blob, wrongKeyPair.privateKey)).rejects.toThrow();
  });
});

// ─── Selective Encryption ────────────────────────────────────────────────────

describe('Selective Encryption', () => {
  const sampleConfig: FullConfig = {
    envelopeVersion: 2,
    id: '550e8400-e29b-41d4-a716-446655440000',
    version: 42,
    teamId: 'team-xyz',
    orgId: 'org-abc',
    sdkEpoch: 5913166,
    lastModified: '2026-03-19T20:00:00Z',
    commitments: { alg: 'HMAC-SHA256', fckSalt: '', fields: {} },
    machines: { server1: { ip: '10.0.0.1', port: 22 } },
    repositories: { myapp: { guid: 'abc-123', credential: 'secret' } },
    storages: { s3: { endpoint: 'https://s3.example.com', key: 'AKID' } },
    ssh: { privateKey: '-----BEGIN OPENSSH PRIVATE KEY-----...' },
  };

  it('round-trip preserves all data', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();
    const epoch = 5913166;

    const payload = await selectiveEncrypt(sampleConfig, sdkKey, cek, {
      sdkEpoch: epoch,
      commitEntries: [],
    });
    const result = await selectiveDecrypt(payload, cek, sdkKey);

    expect(result.id).toBe(sampleConfig.id);
    expect(result.version).toBe(sampleConfig.version);
    expect(result.teamId).toBe(sampleConfig.teamId);
    expect(result.machines).toEqual(sampleConfig.machines);
    expect(result.ssh).toEqual(sampleConfig.ssh);
    expect(result.repositories).toEqual(sampleConfig.repositories);
    expect(result.storages).toEqual(sampleConfig.storages);
  });

  it('envelope contains plaintext fields', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();

    const payload = await selectiveEncrypt(sampleConfig, sdkKey, cek, {
      sdkEpoch: 5913166,
      commitEntries: [],
    });
    expect(payload.envelope.id).toBe(sampleConfig.id);
    expect(payload.envelope.version).toBe(42);
    expect(payload.envelope.sdkEpoch).toBe(5913166);
    expect(payload.envelope.teamId).toBe('team-xyz');
    expect(payload.envelope.envelopeVersion).toBe(2);
    expect(payload.envelope.commitments.alg).toBe('HMAC-SHA256');
  });

  it('encrypted blob does not contain plaintext sensitive data', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();

    const payload = await selectiveEncrypt(sampleConfig, sdkKey, cek, {
      sdkEpoch: 5913166,
      commitEntries: [],
    });
    expect(payload.encryptedBlob).not.toContain('10.0.0.1');
    expect(payload.encryptedBlob).not.toContain('PRIVATE KEY');
    expect(payload.encryptedBlob).not.toContain('secret');
  });

  it('tampered blob fails HMAC verification', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();

    const payload = await selectiveEncrypt(sampleConfig, sdkKey, cek, {
      sdkEpoch: 5913166,
      commitEntries: [],
    });
    payload.encryptedBlob = `${payload.encryptedBlob.slice(0, -4)}XXXX`; // tamper

    await expect(selectiveDecrypt(payload, cek, sdkKey)).rejects.toThrow(/integrity check failed/);
  });

  it('handles config with missing optional fields', async () => {
    const minimalConfig: FullConfig = {
      envelopeVersion: 2,
      id: 'minimal-id',
      version: 1,
      sdkEpoch: 1,
      commitments: { alg: 'HMAC-SHA256', fckSalt: '', fields: {} },
    };

    const sdkKey = await generateAesKey();
    const cek = await generateCek();

    const payload = await selectiveEncrypt(minimalConfig, sdkKey, cek, {
      sdkEpoch: 1,
      commitEntries: [],
    });
    const result = await selectiveDecrypt(payload, cek, sdkKey);
    expect(result.id).toBe('minimal-id');
    expect(result.version).toBe(1);
    expect(result.machines).toBeUndefined();
    expect(result.ssh).toBeUndefined();
  });

  it('envelope v2 stores field commitments for sensitive paths', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();

    const payload = await selectiveEncrypt(sampleConfig, sdkKey, cek, {
      sdkEpoch: 1,
      commitEntries: [
        { pointer: '/machines/server1/ip', value: '10.0.0.1' },
        { pointer: '/ssh/privateKey', value: sampleConfig.ssh?.privateKey },
      ],
    });

    expect(payload.envelope.commitments.fields['/machines/server1/ip']).toBeDefined();
    expect(payload.envelope.commitments.fields['/ssh/privateKey']).toBeDefined();
    expect(payload.envelope.commitments.fckSalt).not.toBe('');
    expect(payload.envelope.commitments.fields['/machines/server1/ip'].kind).toBe('string');
  });

  it('selectiveDecrypt rejects v1 envelopes', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();

    const payload = await selectiveEncrypt(sampleConfig, sdkKey, cek, {
      sdkEpoch: 1,
      commitEntries: [],
    });
    // Simulate a v1 envelope arriving from the wire.
    const v1Payload = {
      ...payload,
      envelope: { ...payload.envelope, envelopeVersion: 1 as unknown as 2 },
    };
    await expect(selectiveDecrypt(v1Payload, cek, sdkKey)).rejects.toThrow(
      /Unsupported envelope version/
    );
  });
});

// ─── Full Lifecycle Integration ──────────────────────────────────────────────

describe('Full Lifecycle', () => {
  it('simulates complete push → pull cycle', async () => {
    // Setup phase (once per org)
    const sdkMaster = generateSdkMaster();
    const serverSecret = generateServerSecret();
    const orgPassphrase = randomBytes(32);
    const passkeySecret = randomBytes(32);
    const cek = await generateCek();

    // Derive wrapping key and wrap CEK
    const wrappingKey = await deriveWrappingKey(passkeySecret, serverSecret);
    const wrappedCEK = await cekWrap(cek, wrappingKey);

    // ── PUSH ──
    const epoch = sdkGetEpoch();
    const sdkDerived = await sdkDerive(sdkMaster, epoch);

    // CLI unwraps CEK
    const unwrappedCek = await cekUnwrap(wrappedCEK, wrappingKey);

    // CLI encrypts config (Layer 1: SDK, Layer 2: CEK)
    const config: FullConfig = {
      envelopeVersion: 2,
      id: 'push-test',
      version: 1,
      sdkEpoch: epoch,
      commitments: { alg: 'HMAC-SHA256', fckSalt: '', fields: {} },
      machines: { prod: { ip: '192.168.1.1' } },
      ssh: { key: 'ssh-ed25519 AAAA...' },
    };

    const payload = await selectiveEncrypt(config, sdkDerived, unwrappedCek, {
      sdkEpoch: epoch,
      commitEntries: [{ pointer: '/machines/prod/ip', value: '192.168.1.1' }],
    });

    // Server encrypts (Layer 3: Org)
    const stored = await orgEncrypt(payload.encryptedBlob, orgPassphrase);

    // ── PULL ──
    // Server decrypts Layer 3
    const afterOrg = await orgDecrypt(stored, orgPassphrase);

    // Server re-derives SDK for the stored epoch
    const sdkDerivedPull = await sdkDerive(sdkMaster, epoch);

    // CLI unwraps CEK (same wrapping key)
    const cekPull = await cekUnwrap(wrappedCEK, wrappingKey);

    // CLI verifies HMAC and decrypts
    // Re-compute HMAC for the server-decrypted blob (same as original client-encrypted blob)
    // Note: afterOrg should equal payload.encryptedBlob since orgEncrypt/orgDecrypt is a round-trip
    expect(afterOrg).toBe(payload.encryptedBlob);

    const result = await selectiveDecrypt(
      { envelope: payload.envelope, encryptedBlob: afterOrg, hmac: payload.hmac },
      cekPull,
      sdkDerivedPull
    );

    expect(result.id).toBe('push-test');
    expect(result.version).toBe(1);
    expect(result.machines).toEqual({ prod: { ip: '192.168.1.1' } });
    expect(result.ssh).toEqual({ key: 'ssh-ed25519 AAAA...' });
  });

  it('different SDK epochs produce different encryption', async () => {
    const sdkMaster = generateSdkMaster();
    const cek = await generateCek();

    const sdk1 = await sdkDerive(sdkMaster, 100);
    const sdk2 = await sdkDerive(sdkMaster, 101);

    const plaintext = 'same data';
    const enc1 = await configEncrypt(plaintext, sdk1, cek);
    const enc2 = await configEncrypt(plaintext, sdk2, cek);

    expect(enc1).not.toBe(enc2);

    // Each can only be decrypted with its own SDK
    expect(await configDecrypt(enc1, cek, sdk1)).toBe(plaintext);
    expect(await configDecrypt(enc2, cek, sdk2)).toBe(plaintext);
    await expect(configDecrypt(enc1, cek, sdk2)).rejects.toThrow();
  });

  it('member addition via X25519 handoff', async () => {
    // Admin has CEK
    const cek = await generateCek();
    const cekRaw = await exportAesKey(cek);

    // New member generates X25519 key pair
    const memberKeyPair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, [
      'deriveBits',
    ])) as unknown as { publicKey: CryptoKey; privateKey: CryptoKey };

    // Admin encrypts CEK for new member
    const handoff = await cekHandoffEncrypt(cekRaw, memberKeyPair.publicKey);

    // New member decrypts CEK
    const memberCekRaw = await cekHandoffDecrypt(handoff, memberKeyPair.privateKey);
    const memberCek = await importAesKey(memberCekRaw);

    // Both can encrypt/decrypt with the same CEK
    const sdkKey = await generateAesKey();
    const encrypted = await configEncrypt('shared secret', sdkKey, cek);
    const decrypted = await configDecrypt(encrypted, memberCek, sdkKey);
    expect(decrypted).toBe('shared secret');
  });

  it('envelope fields readable without decryption', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();

    const config: FullConfig = {
      envelopeVersion: 2,
      id: 'readable-id',
      version: 99,
      sdkEpoch: 12345,
      teamId: 'team-123',
      commitments: { alg: 'HMAC-SHA256', fckSalt: '', fields: {} },
      machines: { secret: { ip: '10.0.0.1' } },
    };

    const payload = await selectiveEncrypt(config, sdkKey, cek, {
      sdkEpoch: 12345,
      commitEntries: [],
    });

    // Server can read envelope without any keys
    expect(payload.envelope.id).toBe('readable-id');
    expect(payload.envelope.version).toBe(99);
    expect(payload.envelope.sdkEpoch).toBe(12345);
    expect(payload.envelope.teamId).toBe('team-123');

    // Server can do version conflict check
    const storedVersion = 98;
    expect(payload.envelope.version).toBeGreaterThan(storedVersion); // accept
  });
});
