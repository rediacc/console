/**
 * The master-password service (PLAN-config-sealed-local.md W2, D2 and D8): the v2 verifier under the
 * 600k kdf, one PBKDF2 per process, the legacy verifier check, the resolution order, and the
 * set/change/remove transitions of `configService.setMasterPassword` with the fields re-sealed in
 * one write. Secure storage is an in-memory fake; every password is a fixed throwaway.
 */
import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import { createEmptyRdcConfig, type RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { configFileStorage } from '../../../adapters/config-file-storage.js';
import { clearSealKeyCache, newSealKdf } from '../../../adapters/config-seal-key.js';
import { nodeCryptoProvider } from '../../../adapters/crypto.js';
import { AuthError } from '../../../utils/errors.js';
import { configService } from '../../config/config-resources.js';
import {
  checkVerifier,
  clearMasterPasswordCache,
  isVerifiedMasterPassword,
  makeVerifier,
  rememberMasterPassword,
  requireMasterPassword,
} from '../master-password.js';

const secureMem = new Map<string, string>();
vi.mock('../../../utils/secure-storage.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/secure-storage.js')>()),
  getSecureStorage: () => ({
    type: 'fake-native',
    get: (key: string) => Promise.resolve(secureMem.get(key) ?? null),
    getSync: (key: string) => secureMem.get(key) ?? null,
    set: (key: string, value: string) => {
      secureMem.set(key, value);
      return Promise.resolve();
    },
    delete: (key: string) => {
      secureMem.delete(key);
      return Promise.resolve();
    },
  }),
}));

const CONFIG_ID = '11111111-2222-4333-8444-555555555555';
const PASSWORD = 'throwaway-password-mp-01';
const OTHER = 'throwaway-password-mp-02';
const DNS_TOKEN = 'throwaway-dns-token-mp-03';

function withVerifier(verifier: string, kdf?: ReturnType<typeof newSealKdf>): RdcConfig {
  return {
    ...createEmptyRdcConfig(),
    id: CONFIG_ID,
    credentials: { masterPasswordVerifier: verifier },
    encryption: { mode: 'master-password', kdf },
  } as RdcConfig;
}

beforeEach(() => {
  clearSealKeyCache();
  clearMasterPasswordCache();
  secureMem.clear();
  vi.stubEnv('REDIACC_MASTER_PASSWORD', '');
  vi.stubEnv('REDIACC_SECRET_STORE', '');
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('verifier v2', () => {
  it('opens under the right password and refuses a wrong one', async () => {
    const kdf = newSealKdf();
    expect(kdf.iterations).toBe(600000);
    const verifier = await makeVerifier(CONFIG_ID, kdf, PASSWORD);
    expect(verifier).toMatch(/^v2:/);
    expect(verifier).not.toContain(PASSWORD);
    expect(await checkVerifier(CONFIG_ID, verifier, kdf, PASSWORD)).toBe(true);
    expect(await checkVerifier(CONFIG_ID, verifier, kdf, OTHER)).toBe(false);
    // Without its kdf a v2 verifier cannot be checked at all.
    expect(await checkVerifier(CONFIG_ID, verifier, undefined, PASSWORD)).toBe(false);
  });

  it('derives K_pw once per process; the control with the cache cleared derives again', async () => {
    const derive = vi.spyOn(nodeCryptoProvider, 'deriveKeyBytes');
    const kdf = newSealKdf();
    const verifier = await makeVerifier(CONFIG_ID, kdf, PASSWORD);
    for (let i = 0; i < 5; i++) {
      expect(await checkVerifier(CONFIG_ID, verifier, kdf, PASSWORD)).toBe(true);
    }
    expect(derive).toHaveBeenCalledTimes(1);

    clearSealKeyCache();
    await checkVerifier(CONFIG_ID, verifier, kdf, PASSWORD);
    expect(derive).toHaveBeenCalledTimes(2);
  });

  it('a legacy (100k, password under itself) verifier still checks', async () => {
    const legacy = await nodeCryptoProvider.encrypt(PASSWORD, PASSWORD);
    expect(await checkVerifier(CONFIG_ID, legacy, undefined, PASSWORD)).toBe(true);
    expect(await checkVerifier(CONFIG_ID, legacy, undefined, OTHER)).toBe(false);
  });
});

describe('requireMasterPassword', () => {
  it('a wrong REDIACC_MASTER_PASSWORD against a v2 verifier is an auth error', async () => {
    const kdf = newSealKdf();
    const config = withVerifier(await makeVerifier(CONFIG_ID, kdf, PASSWORD), kdf);
    vi.stubEnv('REDIACC_MASTER_PASSWORD', OTHER);
    await expect(requireMasterPassword(config)).rejects.toBeInstanceOf(AuthError);
    vi.stubEnv('REDIACC_MASTER_PASSWORD', PASSWORD);
    expect(await requireMasterPassword(config)).toBe(PASSWORD);
    expect(isVerifiedMasterPassword(CONFIG_ID, config.credentials!.masterPasswordVerifier!)).toBe(
      true
    );
  });

  it('a legacy verifier the environment password does not open is accepted unchecked and never marked verified', async () => {
    const legacy = await nodeCryptoProvider.encrypt(PASSWORD, PASSWORD);
    vi.stubEnv('REDIACC_MASTER_PASSWORD', OTHER);
    expect(await requireMasterPassword(withVerifier(legacy))).toBe(OTHER);
    expect(isVerifiedMasterPassword(CONFIG_ID, legacy)).toBe(false);

    vi.stubEnv('REDIACC_MASTER_PASSWORD', PASSWORD);
    expect(await requireMasterPassword(withVerifier(legacy))).toBe(PASSWORD);
    expect(isVerifiedMasterPassword(CONFIG_ID, legacy)).toBe(true);
  });

  it('a password remembered for a new verifier wins over the environment variable', async () => {
    const kdf = newSealKdf();
    const verifier = await makeVerifier(CONFIG_ID, kdf, OTHER);
    rememberMasterPassword(CONFIG_ID, verifier, OTHER);
    vi.stubEnv('REDIACC_MASTER_PASSWORD', PASSWORD);
    expect(await requireMasterPassword(withVerifier(verifier, kdf))).toBe(OTHER);
  });

  it('with no TTY and no environment password it refuses instead of prompting', async () => {
    const kdf = newSealKdf();
    const config = withVerifier(await makeVerifier(CONFIG_ID, kdf, PASSWORD), kdf);
    const isTTY = process.stdin.isTTY;
    Object.defineProperty(process.stdin, 'isTTY', { value: false, configurable: true });
    try {
      await expect(requireMasterPassword(config)).rejects.toThrow(/non-interactive/);
    } finally {
      Object.defineProperty(process.stdin, 'isTTY', { value: isTTY, configurable: true });
    }
  });
});

describe('configService.setMasterPassword (D8 transitions)', () => {
  let name: string;

  async function raw(): Promise<RdcConfig> {
    return JSON.parse(
      await fs.readFile(configFileStorage.getConfigPath(name), 'utf-8')
    ) as RdcConfig;
  }

  async function seed(config: Partial<RdcConfig>): Promise<void> {
    await fs.mkdir(configFileStorage.getConfigDir(), { recursive: true });
    await fs.writeFile(
      join(configFileStorage.getConfigDir(), `${name}.json`),
      JSON.stringify({ ...createEmptyRdcConfig(), id: CONFIG_ID, ...config }),
      { mode: 0o600 }
    );
    configFileStorage.clearCache();
  }

  /** A new process: nothing remembered, so the environment password is the only way in. */
  function freshProcess(password: string): void {
    clearSealKeyCache();
    clearMasterPasswordCache();
    configFileStorage.clearCache();
    vi.stubEnv('REDIACC_MASTER_PASSWORD', password);
  }

  beforeEach(() => {
    name = `mp-${Math.random().toString(36).slice(2, 10)}`;
  });

  it('set, change and remove on a local config: plaintext -> master-password -> new password -> plaintext', async () => {
    await seed({ credentials: { cfDnsApiToken: DNS_TOKEN }, encryption: { mode: 'plaintext' } });

    await configService.setMasterPassword(PASSWORD, name);
    const set = await raw();
    expect(set.encryption?.mode).toBe('master-password');
    expect(set.credentials?.masterPasswordVerifier).toMatch(/^v2:/);
    expect(JSON.stringify(set)).not.toContain(DNS_TOKEN);
    const firstSalt = set.encryption?.kdf?.salt;

    freshProcess(PASSWORD);
    await configService.setMasterPassword(OTHER, name);
    const changed = await raw();
    expect(changed.encryption?.kdf?.salt).not.toBe(firstSalt);
    expect(JSON.stringify(changed)).not.toContain(DNS_TOKEN);

    freshProcess(PASSWORD);
    await expect(configFileStorage.loadDecrypted(name)).rejects.toBeInstanceOf(AuthError);
    freshProcess(OTHER);
    expect((await configFileStorage.loadDecrypted(name)).credentials?.cfDnsApiToken).toBe(
      DNS_TOKEN
    );

    await configService.setMasterPassword(null, name);
    const removed = await raw();
    expect(removed.encryption?.mode).toBe('plaintext');
    expect(removed.encryption?.kdf).toBeUndefined();
    expect(removed.credentials?.masterPasswordVerifier).toBeUndefined();
    expect(removed.credentials?.cfDnsApiToken).toBe(DNS_TOKEN);
  });

  it('set and remove on a keyring-sealed remote config: keyring -> keyring+master-password -> keyring', async () => {
    await seed({
      remote: {
        apiUrl: 'https://account.example.invalid',
        storeId: '22222222-3333-4444-8555-666666666666',
        configId: '33333333-4444-4555-8666-777777777777',
        storageKeyId: 'rdc:slot:throwaway',
      },
      credentials: { cfDnsApiToken: DNS_TOKEN },
      encryption: { mode: 'plaintext' },
    });
    await configFileStorage.updateCache(name, (config) => config);
    const keyringId = (await raw()).encryption?.keyringId;
    expect((await raw()).encryption?.mode).toBe('keyring');

    await configService.setMasterPassword(PASSWORD, name);
    const stacked = await raw();
    expect(stacked.encryption?.mode).toBe('keyring+master-password');
    expect(stacked.encryption?.keyringId).toBe(keyringId);
    expect(JSON.stringify(stacked)).not.toContain(DNS_TOKEN);

    freshProcess(PASSWORD);
    await configService.setMasterPassword(null, name);
    const keyringOnly = await raw();
    expect(keyringOnly.encryption?.mode).toBe('keyring');
    expect(keyringOnly.encryption?.kdf).toBeUndefined();
    expect(JSON.stringify(keyringOnly)).not.toContain(DNS_TOKEN);

    freshProcess('');
    expect((await configFileStorage.loadDecrypted(name)).credentials?.cfDnsApiToken).toBe(
      DNS_TOKEN
    );
  });
});
