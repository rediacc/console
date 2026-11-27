/**
 * The v2 field seal (PLAN-config-sealed-local.md D1, D2, D7): keyring, master-password and stacked
 * modes; AAD binding a blob to its pointer and its keyring key; the legacy 100k blob read and its
 * re-seal; and the device-local-vs-encryptAtRest invariant. Secure storage is the opt-in file backend
 * under the per-file throwaway state home; every key and password here is a fixed throwaway.
 */
import type { RdcConfig } from '@rediacc/shared/config-schema';
import {
  createEmptyRdcConfig,
  DEVICE_LOCAL_POINTERS,
  deviceLocalSealedTemplates,
  isSealed,
  SENSITIVITY_REGISTRY,
} from '@rediacc/shared/config-schema';
import { ENCRYPTION_CONFIG } from '@rediacc/shared/encryption';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  decryptConfigFields,
  encryptConfigFields,
  injectEncryptedStubs,
} from '../config-field-crypto.js';
import { clearSealKeyCache, dropKey, mintKey, SealKeyLostError } from '../config-seal-key.js';
import { nodeCryptoProvider } from '../crypto.js';

const PRIVATE_KEY = 'throwaway-private-key-material-0001';
const DNS_TOKEN = 'throwaway-dns-token-0002';
const PASSWORD = 'throwaway-password-0003';

function fixture(encryption: RdcConfig['encryption']): RdcConfig {
  return {
    ...createEmptyRdcConfig(),
    id: '11111111-2222-4333-8444-555555555555',
    credentials: { ssh: { privateKey: PRIVATE_KEY }, cfDnsApiToken: DNS_TOKEN },
    encryption,
  } as RdcConfig;
}

function raw(config: RdcConfig): string {
  return JSON.stringify(config);
}

beforeAll(() => {
  vi.stubEnv('REDIACC_SECRET_STORE', 'file');
});
afterAll(() => {
  vi.unstubAllEnvs();
});
beforeEach(() => {
  clearSealKeyCache();
});

describe('keyring mode', () => {
  it('seals every encrypt-at-rest leaf as a v2 blob and opens it again', async () => {
    const keyringId = await mintKey();
    const sealed = await encryptConfigFields(
      fixture({ mode: 'keyring', keyringId, sealOptOut: false })
    );
    expect(raw(sealed)).not.toContain(PRIVATE_KEY);
    expect(raw(sealed)).not.toContain(DNS_TOKEN);
    const fields = sealed.encryption?.encryptedFields ?? {};
    expect(Object.keys(fields).sort((a, b) => a.localeCompare(b))).toEqual([
      '/credentials/cfDnsApiToken',
      '/credentials/ssh/privateKey',
    ]);
    expect(Object.values(fields).every((blob) => blob.v === 2)).toBe(true);
    expect(sealed.encryption?.keyringId).toBe(keyringId);
    expect(sealed.encryption?.sealOptOut).toBe(false);
    expect(sealed.encryption?.kdf).toBeUndefined();

    clearSealKeyCache();
    const opened = await decryptConfigFields(injectEncryptedStubs(sealed));
    expect(opened.credentials?.ssh?.privateKey).toBe(PRIVATE_KEY);
    expect(opened.credentials?.cfDnsApiToken).toBe(DNS_TOKEN);
    expect(opened.encryption?.keyringId).toBe(keyringId);
  });

  it('control (AAD): a blob moved to another pointer does not open', async () => {
    const keyringId = await mintKey();
    const sealed = await encryptConfigFields(fixture({ mode: 'keyring', keyringId }));
    const fields = sealed.encryption!.encryptedFields!;
    const swapped: RdcConfig = {
      ...sealed,
      encryption: {
        ...sealed.encryption!,
        encryptedFields: {
          '/credentials/ssh/privateKey': fields['/credentials/cfDnsApiToken'],
          '/credentials/cfDnsApiToken': fields['/credentials/ssh/privateKey'],
        },
      },
    };
    await expect(decryptConfigFields(swapped)).rejects.toBeInstanceOf(SealKeyLostError);
  });

  it('control (AAD): blobs under one keyringId do not open under another key', async () => {
    const first = await mintKey();
    const sealed = await encryptConfigFields(fixture({ mode: 'keyring', keyringId: first }));
    const second = await mintKey();
    const moved: RdcConfig = {
      ...sealed,
      encryption: { ...sealed.encryption!, keyringId: second },
    };
    const error = await decryptConfigFields(moved).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(SealKeyLostError);
    expect((error as SealKeyLostError).reason).toBe('auth');
  });

  it('a damaged blob under a key that opens the others is not key loss', async () => {
    const keyringId = await mintKey();
    const sealed = await encryptConfigFields(fixture({ mode: 'keyring', keyringId }));
    const fields = sealed.encryption!.encryptedFields!;
    const flipped = Buffer.from(fields['/credentials/ssh/privateKey'].data, 'base64');
    flipped[flipped.length - 1] ^= 0xff;
    const damaged: RdcConfig = {
      ...sealed,
      encryption: {
        ...sealed.encryption!,
        encryptedFields: {
          ...fields,
          '/credentials/ssh/privateKey': { v: 2, data: flipped.toString('base64') },
        },
      },
    };
    const error = await decryptConfigFields(damaged).catch((e: unknown) => e);
    expect(error).not.toBeInstanceOf(SealKeyLostError);
    expect((error as Error).message).toMatch(/damaged/);
  });

  it('a damaged blob that precedes the openable ones is not key loss either', async () => {
    const keyringId = await mintKey();
    const sealed = await encryptConfigFields(fixture({ mode: 'keyring', keyringId }));
    const fields = sealed.encryption!.encryptedFields!;
    const first = Buffer.from(fields['/credentials/cfDnsApiToken'].data, 'base64');
    first[first.length - 1] ^= 0xff;
    const damaged: RdcConfig = {
      ...sealed,
      encryption: {
        ...sealed.encryption!,
        encryptedFields: {
          '/credentials/cfDnsApiToken': { v: 2, data: first.toString('base64') },
          '/credentials/ssh/privateKey': fields['/credentials/ssh/privateKey'],
        },
      },
    };
    const error = await decryptConfigFields(damaged).catch((e: unknown) => e);
    expect(error).not.toBeInstanceOf(SealKeyLostError);
    expect((error as Error).message).toMatch(/damaged/);
  });

  it('a truncated ciphertext is damage, never key loss', async () => {
    const keyringId = await mintKey();
    const sealed = await encryptConfigFields(fixture({ mode: 'keyring', keyringId }));
    const truncated: RdcConfig = {
      ...sealed,
      encryption: {
        ...sealed.encryption!,
        encryptedFields: { '/credentials/ssh/privateKey': { v: 2, data: 'AAAA' } },
      },
    };
    const error = await decryptConfigFields(truncated).catch((e: unknown) => e);
    expect(error).not.toBeInstanceOf(SealKeyLostError);
    expect((error as Error).message).toMatch(/damaged/);
  });

  it('raises SealKeyLostError (missing) when secure storage lost the key', async () => {
    const keyringId = await mintKey();
    const sealed = await encryptConfigFields(fixture({ mode: 'keyring', keyringId }));
    await dropKey(keyringId);
    clearSealKeyCache();
    const error = await decryptConfigFields(sealed).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(SealKeyLostError);
    expect((error as SealKeyLostError).reason).toBe('missing');
    expect((error as Error).message).not.toContain(PRIVATE_KEY);
  });

  it('carries a stub leaf only when its blob opens under the current key', async () => {
    const first = await mintKey();
    const sealed = await encryptConfigFields(fixture({ mode: 'keyring', keyringId: first }));
    const stubbed = injectEncryptedStubs(sealed);
    const again = await encryptConfigFields(stubbed);
    expect(again.encryption?.encryptedFields).toEqual(sealed.encryption?.encryptedFields);

    const second = await mintKey();
    const resealedBlind: RdcConfig = {
      ...stubbed,
      encryption: { ...stubbed.encryption!, keyringId: second },
    };
    await expect(encryptConfigFields(resealedBlind)).rejects.toThrow(
      /not sealed under the current key/
    );
  });

  it('public stubs parse without touching secure storage', async () => {
    const keyringId = await mintKey();
    const sealed = await encryptConfigFields(fixture({ mode: 'keyring', keyringId }));
    await dropKey(keyringId);
    clearSealKeyCache();
    const stubbed = injectEncryptedStubs(sealed);
    expect(stubbed.credentials?.ssh?.privateKey).toBe('<encrypted:/credentials/ssh/privateKey>');
    expect(isSealed(stubbed)).toBe(true);
  });
});

describe('master-password and stacked modes', () => {
  it('master-password mode gets a 600k kdf and v2 blobs that need the password', async () => {
    const sealed = await encryptConfigFields(fixture({ mode: 'master-password' }), PASSWORD);
    expect(sealed.encryption?.kdf?.iterations).toBe(600000);
    expect(sealed.encryption?.kdf?.alg).toBe('pbkdf2-sha256');
    expect(raw(sealed)).not.toContain(PASSWORD);
    clearSealKeyCache();
    await expect(decryptConfigFields(sealed, 'throwaway-wrong-password')).rejects.toThrow(
      /wrong master password/
    );
    const opened = await decryptConfigFields(sealed, PASSWORD);
    expect(opened.credentials?.ssh?.privateKey).toBe(PRIVATE_KEY);
  });

  it('stacked: the right key with the wrong password fails, and the right password with the wrong key fails', async () => {
    const keyringId = await mintKey();
    const sealed = await encryptConfigFields(
      fixture({ mode: 'keyring+master-password', keyringId }),
      PASSWORD
    );
    expect(sealed.encryption?.kdf).toBeDefined();
    expect((await decryptConfigFields(sealed, PASSWORD)).credentials?.cfDnsApiToken).toBe(
      DNS_TOKEN
    );

    // At this layer a wrong password under a keyring key reads as an auth failure; the caller checks
    // the password against its verifier before unsealing, so only a lost key reaches the recovery.
    await expect(decryptConfigFields(sealed, 'throwaway-wrong-password')).rejects.toBeInstanceOf(
      SealKeyLostError
    );

    const other = await mintKey();
    const otherKey: RdcConfig = {
      ...sealed,
      encryption: { ...sealed.encryption!, keyringId: other },
    };
    await expect(decryptConfigFields(otherKey, PASSWORD)).rejects.toBeInstanceOf(SealKeyLostError);
  });
});

describe('nodeCryptoProvider.deriveKey', () => {
  it('keeps the legacy 100k default, so a caller that passes no count derives the key it always did', async () => {
    const { pbkdf2Sync } = await import('node:crypto');
    const salt = Buffer.alloc(16, 7);
    const expected = pbkdf2Sync(PASSWORD, salt, 100000, 32, 'sha256').toString('base64');
    expect(await nodeCryptoProvider.deriveKey(PASSWORD, salt)).toBe(expected);
  });
});

describe('legacy blobs (per-blob PBKDF2, 100k)', () => {
  async function legacyConfig(): Promise<RdcConfig> {
    const data = await nodeCryptoProvider.encrypt(JSON.stringify(PRIVATE_KEY), PASSWORD);
    return {
      ...createEmptyRdcConfig(),
      id: '11111111-2222-4333-8444-555555555555',
      // The leaf's container exists: a blob whose container is gone is dropped by design.
      credentials: { ssh: {} },
      encryption: {
        mode: 'master-password',
        encryptedFields: { '/credentials/ssh/privateKey': { data } },
      },
    } as RdcConfig;
  }

  it('the legacy count stays 100k, and the password-derived count is 600k', () => {
    expect(ENCRYPTION_CONFIG.LEGACY_ITERATIONS).toBe(100000);
    expect(ENCRYPTION_CONFIG.ITERATIONS).toBe(600000);
  });

  it('a legacy 100k blob decrypts', async () => {
    const opened = await decryptConfigFields(await legacyConfig(), PASSWORD);
    expect(opened.credentials?.ssh?.privateKey).toBe(PRIVATE_KEY);
  });

  it('control: the same blob read as v2 fails', async () => {
    const legacy = await legacyConfig();
    const blob = legacy.encryption!.encryptedFields!['/credentials/ssh/privateKey'];
    const asV2: RdcConfig = {
      ...legacy,
      encryption: {
        mode: 'master-password',
        kdf: { alg: 'pbkdf2-sha256', iterations: 600000, salt: 'AAAAAAAAAAAAAAAAAAAAAA==' },
        encryptedFields: { '/credentials/ssh/privateKey': { v: 2, data: blob.data } },
      },
    };
    await expect(decryptConfigFields(asV2, PASSWORD)).rejects.toThrow(/did not open/);
  });

  it('the next write re-seals a never-decrypted legacy blob as v2', async () => {
    const stubbed = injectEncryptedStubs(await legacyConfig());
    const resealed = await encryptConfigFields(stubbed, PASSWORD);
    const blob = resealed.encryption!.encryptedFields!['/credentials/ssh/privateKey'];
    expect(blob.v).toBe(2);
    expect(resealed.encryption?.kdf?.iterations).toBe(600000);
    const opened = await decryptConfigFields(resealed, PASSWORD);
    expect(opened.credentials?.ssh?.privateKey).toBe(PRIVATE_KEY);
  });

  it('a legacy blob without the password neither opens nor carries', async () => {
    const legacy = await legacyConfig();
    await expect(decryptConfigFields(legacy)).rejects.toThrow(/needs the master password/);
    const keyringId = await mintKey();
    const keyring: RdcConfig = {
      ...injectEncryptedStubs(legacy),
      encryption: { ...legacy.encryption!, mode: 'keyring', keyringId },
    };
    await expect(encryptConfigFields(keyring)).rejects.toThrow(/needs the master password/);
  });
});

describe('a blob whose parent container is missing at rest', () => {
  it('decrypt restores the value, creating the parent, so the next save keeps it', async () => {
    const keyringId = await mintKey();
    const sealed = await encryptConfigFields(fixture({ mode: 'keyring', keyringId }));
    const credentialsWithoutSsh = { ...sealed.credentials };
    delete credentialsWithoutSsh.ssh;
    const parentless: RdcConfig = { ...sealed, credentials: credentialsWithoutSsh };
    const opened = await decryptConfigFields(parentless);
    expect(opened.credentials?.ssh?.privateKey).toBe(PRIVATE_KEY);
    const resealed = await encryptConfigFields(opened);
    expect(Object.keys(resealed.encryption?.encryptedFields ?? {})).toContain(
      '/credentials/ssh/privateKey'
    );
  });
});

describe('device-local vs encryptAtRest invariant (D7)', () => {
  it('no device-local pointer is sealed at rest, so a re-pull restores every sealed leaf', () => {
    expect(deviceLocalSealedTemplates()).toEqual([]);
  });

  it('control: a fixture that seals a device-local leaf is caught, at the pointer and under it', () => {
    const offending = new Map(SENSITIVITY_REGISTRY);
    offending.set('/remote/fixtureSecret', {
      kind: 'secret',
      redactAs: '<redacted:secret>',
      commit: false,
      encryptAtRest: true,
    });
    offending.set('/renetPath', {
      kind: 'secret',
      redactAs: '<redacted:secret>',
      commit: false,
      encryptAtRest: true,
    });
    expect(
      deviceLocalSealedTemplates(offending, DEVICE_LOCAL_POINTERS).sort((a, b) =>
        a.localeCompare(b)
      )
    ).toEqual(['/remote/fixtureSecret', '/renetPath']);
  });
});
