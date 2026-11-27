/**
 * The storage half of the sealed local config (PLAN-config-sealed-local.md W2: D4, D5, D6, D7, D8):
 * seal on next write for remote-enabled configs, cache writes included; the keyring-before-rename
 * order and its rollback; the `.bak` overwrite; the file-store refusal; public reads that touch no
 * secure storage; the stacked mode's two independent failures; the key-loss handler hook; and the
 * legacy-verifier rewrite. Secure storage is an in-memory fake standing in for a native backend;
 * every key and password is a fixed throwaway.
 */
import { promises as fs } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createEmptyRdcConfig, type RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '../../i18n/index.js';
import { clearMasterPasswordCache } from '../../services/core/master-password.js';
import { AuthError } from '../../utils/errors.js';
import { ConfigFileStorage, resetFileStoreRefusalNotice } from '../config-file-storage.js';
import { clearSealKeyCache, SealKeyLostError } from '../config-seal-key.js';
import { nodeCryptoProvider } from '../crypto.js';

const secureMem = new Map<string, string>();
const fakeStorage = {
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
};
const getSecureStorage = vi.fn(() => fakeStorage);

vi.mock('../../utils/secure-storage.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/secure-storage.js')>()),
  getSecureStorage: () => getSecureStorage(),
}));

const PRIVATE_KEY = 'throwaway-private-key-material-w2-01';
const DNS_TOKEN = 'throwaway-dns-token-w2-02';
const PASSWORD = 'throwaway-password-w2-03';
const NAME = 'sealme';

let dir: string;
let storage: ConfigFileStorage;

function remoteFixture(encryption: RdcConfig['encryption'] = { mode: 'plaintext' }): RdcConfig {
  return {
    ...createEmptyRdcConfig(),
    id: '11111111-2222-4333-8444-555555555555',
    remote: {
      apiUrl: 'https://account.example.invalid',
      storeId: '22222222-3333-4444-8555-666666666666',
      configId: '33333333-4444-4555-8666-777777777777',
      storageKeyId: 'rdc:slot:throwaway',
    },
    credentials: { ssh: { privateKey: PRIVATE_KEY }, cfDnsApiToken: DNS_TOKEN },
    encryption,
  } as RdcConfig;
}

function localFixture(): RdcConfig {
  const { remote: _remote, ...local } = remoteFixture();
  return local as RdcConfig;
}

async function writeRaw(config: RdcConfig, name = NAME): Promise<void> {
  await fs.writeFile(join(dir, `${name}.json`), JSON.stringify(config, null, 2), { mode: 0o600 });
}

function rawText(name = NAME): Promise<string> {
  return fs.readFile(join(dir, `${name}.json`), 'utf-8');
}

async function rawConfig(name = NAME): Promise<RdcConfig> {
  return JSON.parse(await rawText(name)) as RdcConfig;
}

function sealKeys(): string[] {
  return [...secureMem.keys()].filter((key) => key.startsWith('rdc:seal:'));
}

/** A cache write that changes nothing, the most common write a remote config sees (a refresh). */
function touchCache(target: ConfigFileStorage = storage, name = NAME): Promise<RdcConfig> {
  return target.updateCache(name, (config) => config);
}

/** A fresh process: no cached key, password or parsed file. */
function freshProcess(): void {
  clearSealKeyCache();
  clearMasterPasswordCache();
  storage.clearCache();
  getSecureStorage.mockClear();
}

beforeEach(async () => {
  dir = await fs.mkdtemp(join(tmpdir(), 'rdc-seal-storage-'));
  storage = new ConfigFileStorage(dir);
  secureMem.clear();
  clearSealKeyCache();
  clearMasterPasswordCache();
  resetFileStoreRefusalNotice();
  getSecureStorage.mockClear();
  vi.stubEnv('REDIACC_SECRET_STORE', '');
  vi.stubEnv('REDIACC_MASTER_PASSWORD', '');
});

afterEach(async () => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  await fs.rm(dir, { recursive: true, force: true });
});

describe('seal on next write (D5)', () => {
  it('a remote config holds no secret on disk after one cache write; a local-only config keeps its plaintext', async () => {
    await writeRaw(remoteFixture());
    await writeRaw(localFixture(), 'local');

    await touchCache();
    await touchCache(storage, 'local');

    const sealed = await rawText();
    expect(sealed).not.toContain(PRIVATE_KEY);
    expect(sealed).not.toContain(DNS_TOKEN);
    const encryption = (await rawConfig()).encryption;
    expect(encryption?.mode).toBe('keyring');
    expect(sealKeys()).toEqual([encryption?.keyringId]);

    // Control: the local-only config is never upgraded.
    const local = await rawText('local');
    expect(local).toContain(PRIVATE_KEY);
    expect((await rawConfig('local')).encryption?.mode).toBe('plaintext');

    // The sealed values open again in a fresh process.
    freshProcess();
    const opened = await storage.loadDecrypted(NAME);
    expect(opened.credentials?.ssh?.privateKey).toBe(PRIVATE_KEY);
    expect(opened.credentials?.cfDnsApiToken).toBe(DNS_TOKEN);
  });

  it('control: a config opted out of sealing stays plaintext', async () => {
    await writeRaw(remoteFixture({ mode: 'plaintext', sealOptOut: true }));
    await touchCache();
    expect(await rawText()).toContain(PRIVATE_KEY);
    expect((await rawConfig()).encryption?.mode).toBe('plaintext');
    expect(sealKeys()).toEqual([]);
  });

  it('overwrites .bak with the sealed bytes, so no plaintext copy stays beside the file', async () => {
    await writeRaw(remoteFixture());
    await touchCache();
    const backup = await fs.readFile(join(dir, `${NAME}.json.bak`), 'utf-8');
    expect(backup).not.toContain(PRIVATE_KEY);
    expect(backup).not.toContain(DNS_TOKEN);
    expect(backup).toBe(await rawText());
  });

  it('stores the key before the rename and deletes it when the write does not land', async () => {
    await writeRaw(remoteFixture());
    const before = await rawText();
    const rename = vi.spyOn(fs, 'rename').mockRejectedValueOnce(new Error('disk full'));

    await expect(touchCache()).rejects.toThrow('disk full');
    expect(rename).toHaveBeenCalledTimes(1);
    expect(sealKeys()).toEqual([]);
    expect(await rawText()).toBe(before);
  });

  it('two concurrent cache writes mint one key', async () => {
    await writeRaw(remoteFixture());
    const other = new ConfigFileStorage(dir);
    await Promise.all([touchCache(storage), touchCache(other)]);
    const keyringId = (await rawConfig()).encryption?.keyringId;
    expect(keyringId).toMatch(/^rdc:seal:/);
    expect(sealKeys()).toEqual([keyringId]);
  });

  it('a later write keeps the key it sealed under', async () => {
    await writeRaw(remoteFixture());
    await touchCache();
    const first = (await rawConfig()).encryption?.keyringId;
    freshProcess();
    await storage.update(NAME, (config) => ({ ...config, renetPath: '/opt/renet' }));
    expect((await rawConfig()).encryption?.keyringId).toBe(first);
    expect(sealKeys()).toEqual([first]);
    expect(await rawText()).not.toContain(PRIVATE_KEY);
  });
});

describe('stale plaintext copies', () => {
  it('saving a stale plaintext copy over a sealed file reuses its key instead of orphaning it', async () => {
    await writeRaw(remoteFixture());
    await touchCache();
    const first = (await rawConfig()).encryption?.keyringId;
    await storage.save(remoteFixture(), NAME);
    expect((await rawConfig()).encryption?.keyringId).toBe(first);
    expect(sealKeys()).toEqual([first]);
  });
});

describe('file-store refusal (D6)', () => {
  it('REDIACC_SECRET_STORE=file keeps the config plaintext and says so once', async () => {
    vi.stubEnv('REDIACC_SECRET_STORE', 'file');
    const stderr = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
    await writeRaw(remoteFixture());

    await touchCache();
    await touchCache();

    expect(await rawText()).toContain(PRIVATE_KEY);
    expect((await rawConfig()).encryption?.mode).toBe('plaintext');
    expect(getSecureStorage).not.toHaveBeenCalled();
    const line = `${t('commands.config.seal.fileStoreRefused', { name: NAME })}\n`;
    expect(stderr.mock.calls.filter(([text]) => text === line)).toHaveLength(1);
  });
});

describe('public reads (D4)', () => {
  it('load() of a sealed config makes no secure-storage call; the loadDecrypted control makes one', async () => {
    await writeRaw(remoteFixture());
    await touchCache();
    freshProcess();

    const pub = await storage.load(NAME);
    expect(pub.remote?.apiUrl).toBe('https://account.example.invalid');
    expect(pub.credentials?.ssh?.privateKey).toMatch(/^<encrypted:/);
    expect(getSecureStorage).toHaveBeenCalledTimes(0);

    const secret = await storage.loadDecrypted(NAME);
    expect(secret.credentials?.ssh?.privateKey).toBe(PRIVATE_KEY);
    expect(getSecureStorage).toHaveBeenCalledTimes(1);
  });
});

describe('stacked mode (keyring+master-password)', () => {
  async function stackedConfig(): Promise<void> {
    vi.stubEnv('REDIACC_MASTER_PASSWORD', PASSWORD);
    await writeRaw(remoteFixture({ mode: 'master-password' }));
    await touchCache();
    const encryption = (await rawConfig()).encryption;
    expect(encryption?.mode).toBe('keyring+master-password');
    expect(encryption?.kdf?.iterations).toBe(600000);
    expect((await rawConfig()).credentials?.masterPasswordVerifier).toMatch(/^v2:/);
    freshProcess();
  }

  it('opens with the right key and the right password', async () => {
    await stackedConfig();
    const opened = await storage.loadDecrypted(NAME);
    expect(opened.credentials?.ssh?.privateKey).toBe(PRIVATE_KEY);
  });

  it('fails with the right key and the wrong password', async () => {
    await stackedConfig();
    vi.stubEnv('REDIACC_MASTER_PASSWORD', 'not-the-password');
    await expect(storage.loadDecrypted(NAME)).rejects.toBeInstanceOf(AuthError);
  });

  it('fails with the right password and the wrong key', async () => {
    await stackedConfig();
    const keyringId = (await rawConfig()).encryption!.keyringId!;
    secureMem.set(keyringId, Buffer.alloc(32, 7).toString('base64'));
    await expect(storage.loadDecrypted(NAME)).rejects.toBeInstanceOf(SealKeyLostError);
  });
});

describe('key loss (D7 hook)', () => {
  it('without a handler the loss propagates as SealKeyLostError (missing)', async () => {
    await writeRaw(remoteFixture());
    await touchCache();
    freshProcess();
    secureMem.clear();
    await expect(storage.loadDecrypted(NAME)).rejects.toMatchObject({
      name: 'SealKeyLostError',
      reason: 'missing',
    });
  });

  it('a registered handler runs once and the read is retried after it', async () => {
    await writeRaw(remoteFixture());
    await touchCache();
    const keyringId = (await rawConfig()).encryption!.keyringId!;
    const key = secureMem.get(keyringId)!;
    freshProcess();
    secureMem.delete(keyringId);

    const handler = vi.fn((_name: string, error: SealKeyLostError) => {
      expect(error.keyringId).toBe(keyringId);
      secureMem.set(keyringId, key);
      return Promise.resolve();
    });
    storage.setSealKeyLostHandler(handler);
    const opened = await storage.loadDecrypted(NAME);
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler.mock.calls[0][0]).toBe(NAME);
    expect(opened.credentials?.cfDnsApiToken).toBe(DNS_TOKEN);
  });
});

describe('legacy verifier (D8)', () => {
  it('a 100k verifier is rewritten as v2 on the next write, and the fields are re-sealed under the new kdf', async () => {
    const legacyVerifier = await nodeCryptoProvider.encrypt(PASSWORD, PASSWORD);
    const legacy = await nodeCryptoProvider.encrypt(JSON.stringify(DNS_TOKEN), PASSWORD);
    const local = localFixture();
    await writeRaw({
      ...local,
      credentials: { ssh: { privateKey: PRIVATE_KEY }, masterPasswordVerifier: legacyVerifier },
      encryption: {
        mode: 'master-password',
        encryptedFields: { '/credentials/cfDnsApiToken': { data: legacy } },
      },
    } as RdcConfig);
    vi.stubEnv('REDIACC_MASTER_PASSWORD', PASSWORD);

    await storage.update(NAME, (config) => config);

    const written = await rawConfig();
    expect(written.credentials?.masterPasswordVerifier).toMatch(/^v2:/);
    expect(written.encryption?.mode).toBe('master-password');
    expect(written.encryption?.kdf?.iterations).toBe(600000);
    const blobs = Object.values(written.encryption?.encryptedFields ?? {});
    expect(blobs.length).toBeGreaterThan(0);
    expect(blobs.every((blob) => blob.v === 2)).toBe(true);
    expect(await rawText()).not.toContain(DNS_TOKEN);

    freshProcess();
    expect((await storage.loadDecrypted(NAME)).credentials?.cfDnsApiToken).toBe(DNS_TOKEN);
  });

  it('a read that verified a legacy verifier writes it back as v2', async () => {
    const legacyVerifier = await nodeCryptoProvider.encrypt(PASSWORD, PASSWORD);
    const legacy = await nodeCryptoProvider.encrypt(JSON.stringify(DNS_TOKEN), PASSWORD);
    await writeRaw({
      ...localFixture(),
      credentials: { masterPasswordVerifier: legacyVerifier },
      encryption: {
        mode: 'master-password',
        encryptedFields: { '/credentials/cfDnsApiToken': { data: legacy } },
      },
    } as RdcConfig);
    vi.stubEnv('REDIACC_MASTER_PASSWORD', PASSWORD);

    const read = await storage.loadDecrypted(NAME);
    expect(read.credentials?.cfDnsApiToken).toBe(DNS_TOKEN);
    expect((await rawConfig()).credentials?.masterPasswordVerifier).toMatch(/^v2:/);
  });
});
