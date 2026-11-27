/**
 * The per-process seal-key cache (PLAN-config-sealed-local.md D3) on a Windows host, where every
 * secure-storage read is one powershell spawn: 50 field reads cost one Unprotect, a public read
 * costs none, and a password is stretched once. powershell is the stand-in from
 * secure-storage.dpapi-timeout.test.ts behind a mocked execFileSync, platform mocked; every key and
 * password here is a fixed throwaway.
 */
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { createEmptyRdcConfig, SEAL_KEYRING_ID } from '@rediacc/shared/config-schema';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const stand = vi.hoisted(() => ({
  protects: 0,
  unprotects: 0,
  stateDir: undefined as string | undefined,
}));

vi.mock('@rediacc/shared/paths', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@rediacc/shared/paths')>();
  return {
    ...actual,
    getRediaccDirs: () => ({ ...actual.getRediaccDirs(), state: stand.stateDir }),
  };
});

vi.mock('node:child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:child_process')>();
  return {
    ...actual,
    execFileSync: (_tool: string, args: string[], options: { input?: string }) => {
      const script = args.at(-1) ?? '';
      if (script.includes('::Unprotect(')) stand.unprotects += 1;
      else if (script.includes('::Protect(')) stand.protects += 1;
      // Protect and Unprotect both answer with the input, which is enough for a round trip.
      return `rdc-dpapi:${options.input}`;
    },
  };
});

const { decryptConfigFields, encryptConfigFields, injectEncryptedStubs } = await import(
  '../config-field-crypto.js'
);
const seal = await import('../config-seal-key.js');
const { nodeCryptoProvider } = await import('../crypto.js');

const platform = Object.getOwnPropertyDescriptor(process, 'platform');

function fixture(keyringId: string): RdcConfig {
  return {
    ...createEmptyRdcConfig(),
    id: '22222222-3333-4444-8555-666666666666',
    credentials: {
      ssh: { privateKey: 'throwaway-private-key-0101' },
      cfDnsApiToken: 'throwaway-token-0102',
    },
    encryption: { mode: 'keyring', keyringId },
  } as RdcConfig;
}

beforeAll(() => {
  vi.stubEnv('REDIACC_SECRET_STORE', '');
  stand.stateDir = mkdtempSync(join(tmpdir(), 'rdc-seal-key-'));
  Object.defineProperty(process, 'platform', { value: 'win32' });
});
afterAll(() => {
  if (platform) Object.defineProperty(process, 'platform', platform);
  vi.unstubAllEnvs();
});
beforeEach(() => {
  seal.clearSealKeyCache();
});

async function sealedFixture(): Promise<RdcConfig> {
  const keyringId = await seal.mintKey();
  const sealed = await encryptConfigFields(fixture(keyringId));
  seal.clearSealKeyCache();
  stand.unprotects = 0;
  stand.protects = 0;
  return injectEncryptedStubs(sealed);
}

describe('seal-key cache on DPAPI', () => {
  it('mints a key under an rdc:seal:<uuid> id and stores it with one Protect', async () => {
    const before = stand.protects;
    const keyringId = await seal.mintKey();
    expect(keyringId).toMatch(SEAL_KEYRING_ID);
    // The backend's proof round trip runs once per process; the mint itself is one Protect beyond it.
    expect(stand.protects - before).toBeGreaterThanOrEqual(1);
  });

  it('50 field reads make exactly 1 Unprotect spawn', async () => {
    const stubbed = await sealedFixture();
    for (let i = 0; i < 50; i++) {
      const opened = await decryptConfigFields(stubbed);
      expect(opened.credentials?.cfDnsApiToken).toBe('throwaway-token-0102');
    }
    expect(stand.unprotects).toBe(1);
  });

  it('control: with the cache cleared midway the same reads make 2', async () => {
    const stubbed = await sealedFixture();
    for (let i = 0; i < 50; i++) {
      if (i === 25) seal.clearSealKeyCache();
      await decryptConfigFields(stubbed);
    }
    expect(stand.unprotects).toBe(2);
  });

  it('a public read through stubs spawns nothing', async () => {
    const stubbed = await sealedFixture();
    const again = injectEncryptedStubs(stubbed);
    expect(again.credentials?.ssh?.privateKey).toBe('<encrypted:/credentials/ssh/privateKey>');
    expect(stand.unprotects + stand.protects).toBe(0);
  });

  it('a missing key is SealKeyLostError, and an absence is not cached', async () => {
    const keyringId = await seal.mintKey();
    await seal.dropKey(keyringId);
    await expect(seal.loadKey('cfg', keyringId)).rejects.toMatchObject({
      name: 'SealKeyLostError',
      reason: 'missing',
      keyringId,
    });
    await seal.writeCachedSecret(keyringId, Buffer.alloc(32, 7).toString('base64'));
    seal.clearSealKeyCache();
    expect((await seal.loadKey('cfg', keyringId)).length).toBe(32);
  });

  it('dropKey refuses an id that is not a seal key', async () => {
    await expect(seal.dropKey('rdc:slot:abc')).rejects.toThrow(/not a seal key id/);
  });

  it('any secret read through the cache (the slot secret, D9) costs one Unprotect per process', async () => {
    const slotKey = 'rdc:slot:throwaway-0201';
    await seal.writeCachedSecret(slotKey, 'throwaway-slot-secret-0202');
    seal.clearSealKeyCache();
    stand.unprotects = 0;
    for (let i = 0; i < 10; i++) {
      expect(await seal.readCachedSecret(slotKey)).toBe('throwaway-slot-secret-0202');
    }
    expect(stand.unprotects).toBe(1);
    await seal.deleteCachedSecret(slotKey);
    expect(await seal.readCachedSecret(slotKey)).toBeNull();
    expect(stand.unprotects).toBe(1);
  });
});

describe('password key cache', () => {
  it('stretches a password once per (config, salt), and again for a different password', async () => {
    const spy = vi.spyOn(nodeCryptoProvider, 'deriveKeyBytes');
    const kdf = {
      alg: 'pbkdf2-sha256' as const,
      iterations: 1000,
      salt: 'AQEBAQEBAQEBAQEBAQEBAQ==',
    };
    const a = await seal.derivePasswordKey('cfg', kdf, 'throwaway-pw-a');
    const a2 = await seal.derivePasswordKey('cfg', kdf, 'throwaway-pw-a');
    expect(a2.equals(a)).toBe(true);
    expect(spy).toHaveBeenCalledTimes(1);
    const b = await seal.derivePasswordKey('cfg', kdf, 'throwaway-pw-b');
    expect(b.equals(a)).toBe(false);
    expect(spy).toHaveBeenCalledTimes(2);
    spy.mockRestore();
  });

  it('a new kdf record uses 600k iterations and a 16-byte salt', () => {
    const kdf = seal.newSealKdf();
    expect(kdf.iterations).toBe(600000);
    expect(Buffer.from(kdf.salt, 'base64').length).toBe(16);
  });
});
