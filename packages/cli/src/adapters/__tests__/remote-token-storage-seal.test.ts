/**
 * Token-file sealing (PLAN-config-sealed-local.md D9): the confidential values of `.tokens/<name>.json`
 * sealed under the slot secret, the anti-rollback counters left readable, a re-enrollment keeping
 * them, a lost slot secret refused with the re-enroll error, and the adapter's slot-secret read
 * served from the per-process cache it shares with the token seal. Every secret here is a fixed
 * throwaway or random per run.
 */
import { promises as fs } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  cekWrap,
  deriveWrappingKey,
  fromBase64,
  generateAesKey,
  randomBytes,
  toBase64,
} from '@rediacc/shared/config-crypto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RemoteConfig } from '../../types/index.js';
import type { TokenLease } from '../remote-token-storage.js';

const store = vi.hoisted(() => ({
  values: new Map<string, string>(),
  gets: 0,
}));

vi.mock('../../utils/secure-storage.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../utils/secure-storage.js')>();
  const storage = {
    type: 'mem',
    get: (key: string) => {
      store.gets += 1;
      return Promise.resolve(store.values.get(key) ?? null);
    },
    getSync: (key: string) => {
      store.gets += 1;
      return store.values.get(key) ?? null;
    },
    set: (key: string, value: string) => {
      store.values.set(key, value);
      return Promise.resolve();
    },
    delete: (key: string) => {
      store.values.delete(key);
      return Promise.resolve();
    },
  };
  return { ...actual, getSecureStorage: () => storage };
});

const { RemoteTokenStorage } = await import('../remote-token-storage.js');
const { RemoteConfigAdapter, RemotePasskeySecretMissingError, RemoteStaleSlotError } = await import(
  '../remote-config-adapter.js'
);
const { clearSealKeyCache } = await import('../config-seal-key.js');
const { getSecureStorage } = await import('../../utils/secure-storage.js');

type Storage = InstanceType<typeof RemoteTokenStorage>;
type SyncRecord = NonNullable<Awaited<ReturnType<Storage['get']>>>['sync'];

const SLOT = 'rdc:slot-0001';
const TOKEN = 'throwaway-config-token-7d1e';
const FCK_SALT = 'throwaway-fck-salt-41aa';
const POLICY_MARK = 'throwaway-policy-member@example.invalid';
const CONFIG_KEY_MARK = 'throwaway-wrapped-config-key-5c2b';

const fullSync = (): NonNullable<SyncRecord> => ({
  binding: 'store-1/config-1/',
  highWater: 7,
  envelopeVersion: 4,
  fckSalt: FCK_SALT,
  configKey: { wrappedConfigKey: CONFIG_KEY_MARK, configKeyVersion: 1 } as never,
  cekGeneration: 3,
  policyHighWater: { 'store-1/config-1/': 2 },
  policyContext: {
    principal: { orgRole: 'owner', userEmail: POLICY_MARK },
    policy: {},
  } as never,
});

/** An in-memory slot-secret source that counts its reads. */
function slotSecrets(initial: Record<string, string> = { [SLOT]: 'slot-secret-one' }) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    reads: 0,
    resets: 0,
    read(id: string) {
      this.reads += 1;
      return Promise.resolve(values.get(id) ?? null);
    },
    reset() {
      this.resets += 1;
    },
  };
}

let dir: string;
const here = () => Promise.resolve('device-here');

beforeEach(async () => {
  dir = await fs.mkdtemp(join(tmpdir(), 'cli-token-seal-'));
  store.values.clear();
  store.gets = 0;
  clearSealKeyCache();
});

afterEach(async () => {
  await fs.rm(dir, { recursive: true, force: true });
});

async function sealedStorage(secrets = slotSecrets()) {
  const storage = new RemoteTokenStorage(dir, here, secrets);
  await storage.set('eu', { token: 'enroll-token', wrappedCek: 'wrapped-cek' });
  await storage.withLease(
    'eu',
    async (lease) => {
      await lease.update(TOKEN);
      await lease.recordSync(fullSync());
    },
    { slotKeyId: SLOT }
  );
  return { storage, secrets };
}

const raw = (name = 'eu') => fs.readFile(join(dir, `${name}.json`), 'utf-8');

describe('the sealed token file', () => {
  it('holds no token, fckSalt, configKey or policyContext text, and its counters stay readable', async () => {
    const { storage } = await sealedStorage();
    const text = await raw();
    for (const secret of [TOKEN, FCK_SALT, POLICY_MARK, CONFIG_KEY_MARK]) {
      expect(text).not.toContain(secret);
    }
    const file = JSON.parse(text);
    expect(file.sealed.v).toBe(1);
    expect(file.slotKeyId).toBe(SLOT);
    expect(file.wrappedCek).toBe('wrapped-cek');
    expect(file.sync).toEqual({
      binding: 'store-1/config-1/',
      highWater: 7,
      envelopeVersion: 4,
      cekGeneration: 3,
      policyHighWater: { 'store-1/config-1/': 2 },
    });
    expect(await storage.get('eu')).toEqual({
      token: TOKEN,
      wrappedCek: 'wrapped-cek',
      sync: fullSync(),
    });
    expect((await fs.stat(join(dir, 'eu.json'))).mode & 0o777).toBe(0o600);
  });

  it('control: a lease that names no slot, on a file never sealed, writes plaintext', async () => {
    const storage = new RemoteTokenStorage(dir, here, slotSecrets());
    await storage.set('eu', { token: 'enroll-token', wrappedCek: 'wrapped-cek' });
    await storage.withLease('eu', (lease) => lease.update(TOKEN));
    expect(JSON.parse(await raw()).token).toBe(TOKEN);
  });

  it('reads a plaintext file written before sealing, and seals it on the next leased write', async () => {
    await fs.writeFile(
      join(dir, 'eu.json'),
      JSON.stringify({ token: TOKEN, wrappedCek: 'wrapped-cek', sync: fullSync() })
    );
    const storage = new RemoteTokenStorage(dir, here, slotSecrets());
    expect((await storage.get('eu'))?.sync?.fckSalt).toBe(FCK_SALT);
    await storage.withLease('eu', (lease) => lease.update('rotated-token-0002'), {
      slotKeyId: SLOT,
    });
    const text = await raw();
    expect(text).not.toContain('rotated-token-0002');
    expect(text).not.toContain(FCK_SALT);
    expect((await storage.get('eu'))?.token).toBe('rotated-token-0002');
  });

  it('a later lease without a slot id keeps sealing under the slot the file records', async () => {
    const { storage } = await sealedStorage();
    await storage.withLease('eu', (lease) => lease.update('rotated-token-0003'));
    expect(await raw()).not.toContain('rotated-token-0003');
    expect((await storage.get('eu'))?.token).toBe('rotated-token-0003');
  });

  it('a sealed file copied to another config name does not open there', async () => {
    const { storage } = await sealedStorage();
    await fs.copyFile(join(dir, 'eu.json'), join(dir, 'us.json'));
    await expect(storage.withLease('us', () => Promise.resolve(1))).rejects.toBeInstanceOf(
      RemoteStaleSlotError
    );
    expect((await storage.get('us'))?.token).toBe('');
  });
});

describe('re-enrollment', () => {
  it('set() keeps the whole sync record (bar cekGeneration) when the sealed file still opens', async () => {
    const { storage, secrets } = await sealedStorage();
    await storage.set('eu', { token: 'reenroll-token', wrappedCek: 'wrapped-cek-2' });
    const { cekGeneration: _dropped, ...kept } = fullSync();
    expect(await storage.get('eu')).toEqual({
      token: 'reenroll-token',
      wrappedCek: 'wrapped-cek-2',
      sync: kept,
    });
    expect(secrets.resets).toBeGreaterThan(0);
  });

  it('set() keeps the counters when the slot secret under the same id was replaced', async () => {
    const { storage, secrets } = await sealedStorage();
    secrets.values.set(SLOT, 'slot-secret-two');
    await storage.set('eu', { token: 'reenroll-token', wrappedCek: 'wrapped-cek-2' });
    const data = await storage.get('eu');
    expect(data?.sync).toEqual({
      binding: 'store-1/config-1/',
      highWater: 7,
      envelopeVersion: 4,
      policyHighWater: { 'store-1/config-1/': 2 },
    });
    expect(data?.token).toBe('reenroll-token');
  });
});

describe('a lost slot secret', () => {
  it('a lease reads it as the re-enroll error, never as an empty record', async () => {
    const { storage, secrets } = await sealedStorage();
    secrets.values.delete(SLOT);
    const fn = vi.fn(() => Promise.resolve(1));
    await expect(storage.withLease('eu', fn)).rejects.toBeInstanceOf(
      RemotePasskeySecretMissingError
    );
    expect(fn).not.toHaveBeenCalled();
  });

  it('get() answers a snapshot with no usable token that set() writes back byte for byte', async () => {
    const { storage, secrets } = await sealedStorage();
    const before = await raw();
    secrets.values.delete(SLOT);
    const snapshot = await storage.get('eu');
    expect(snapshot?.token).toBe('');
    expect(snapshot?.sync?.highWater).toBe(7);
    expect(snapshot?.sync?.fckSalt).toBeUndefined();

    // A re-enrollment stores new credentials, fails, and restores the snapshot.
    await storage.set('eu', { token: 'reenroll-token', wrappedCek: 'wrapped-cek-2' });
    await storage.set('eu', snapshot as NonNullable<typeof snapshot>);
    expect(await raw()).toBe(before);
    secrets.values.set(SLOT, 'slot-secret-one');
    expect((await storage.get('eu'))?.token).toBe(TOKEN);
  });

  it('refuses a sealed write rather than storing the token in plaintext', async () => {
    const secrets = slotSecrets({});
    const storage = new RemoteTokenStorage(dir, here, secrets);
    await storage.set('eu', { token: 'enroll-token', wrappedCek: 'wrapped-cek' });
    await expect(
      storage.withLease('eu', (lease) => lease.update(TOKEN), { slotKeyId: SLOT })
    ).rejects.toBeInstanceOf(RemotePasskeySecretMissingError);
    expect(await raw()).not.toContain(TOKEN);
  });
});

describe('the slot-secret cache (D9)', () => {
  const remote: RemoteConfig = {
    apiUrl: 'https://account.example.invalid',
    storeId: 'store-1',
    configId: 'config-1',
    storageKeyId: SLOT,
  } as RemoteConfig;

  async function wrapped(slotSecret: string, serverSecret: Uint8Array) {
    const cek = await generateAesKey();
    return cekWrap(cek, await deriveWrappingKey(fromBase64(slotSecret), serverSecret));
  }

  type CekDeriver = {
    deriveCek(serverSecret: Uint8Array, lease: { data: { wrappedCek: string } }): Promise<unknown>;
  };

  it('a leased seal and two CEK derivations read the slot secret once', async () => {
    const slotSecret = toBase64(randomBytes(32));
    store.values.set(SLOT, slotSecret);
    const serverSecret = randomBytes(32);
    const wrappedCek = await wrapped(slotSecret, serverSecret);

    const storage = new RemoteTokenStorage(dir, here);
    await storage.set('eu', { token: 'enroll-token', wrappedCek });
    const adapter = new RemoteConfigAdapter(remote, 'eu', storage, getSecureStorage());
    store.gets = 0;
    const leaser = adapter as unknown as {
      leased(fn: (lease: TokenLease) => Promise<void>): Promise<void>;
    };
    await leaser.leased((lease) => lease.update(TOKEN));
    const deriver = adapter as unknown as CekDeriver;
    await deriver.deriveCek(serverSecret, { data: { wrappedCek } });
    await deriver.deriveCek(serverSecret, { data: { wrappedCek } });
    expect(store.gets).toBe(1);
    expect(await raw()).not.toContain(TOKEN);
  });

  it('control: an injected storage is read on every derivation', async () => {
    const slotSecret = toBase64(randomBytes(32));
    const serverSecret = randomBytes(32);
    const wrappedCek = await wrapped(slotSecret, serverSecret);
    const injected = {
      type: 'mem',
      get: vi.fn().mockResolvedValue(slotSecret),
      set: vi.fn(),
      delete: vi.fn(),
    };
    const adapter = new RemoteConfigAdapter(
      remote,
      'eu',
      new RemoteTokenStorage(dir, here),
      injected
    ) as unknown as CekDeriver;
    await adapter.deriveCek(serverSecret, { data: { wrappedCek } });
    await adapter.deriveCek(serverSecret, { data: { wrappedCek } });
    expect(injected.get).toHaveBeenCalledTimes(2);
  });

  it('a cached secret replaced since it was read is read again once, uncached', async () => {
    const oldSecret = toBase64(randomBytes(32));
    const newSecret = toBase64(randomBytes(32));
    const serverSecret = randomBytes(32);
    store.values.set(SLOT, oldSecret);
    const adapter = new RemoteConfigAdapter(
      remote,
      'eu',
      new RemoteTokenStorage(dir, here),
      getSecureStorage()
    ) as unknown as CekDeriver;
    await adapter.deriveCek(serverSecret, {
      data: { wrappedCek: await wrapped(oldSecret, serverSecret) },
    });
    store.values.set(SLOT, newSecret);
    store.gets = 0;
    await adapter.deriveCek(serverSecret, {
      data: { wrappedCek: await wrapped(newSecret, serverSecret) },
    });
    expect(store.gets).toBe(1);
  });
});
