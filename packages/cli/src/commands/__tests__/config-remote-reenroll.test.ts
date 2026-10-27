/**
 * `rdc config remote enable` on a config that is ALREADY linked.
 *
 * The dead end this file pins (operator, 2026-10-13): the slot secret lives in the Linux kernel
 * keyring, which a reboot empties. Every command then failed with "re-authenticate with
 * `rdc config remote enable`", enable refused a linked config and named `disable`, and `disable`
 * needs the same missing secret. Enable now enrolls THIS device again for the same store when its
 * credentials are lost, and still refuses while they work.
 *
 * Real here: the config file storage, the token file storage (both in the throwaway config home of
 * isolate-config-home.ts), the cache merge, the command registration and the re-enroll flow. Faked:
 * the OS secure storage (an in-memory map; a test must never touch a real keyring), the portal
 * relay, the account API, and the adapter, which stands in for the config server and answers the
 * way the real one does for the credentials this device holds at that moment.
 */

import { promises as fs } from 'node:fs';
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { assertThrowawayDir } from '../../__tests__/throwaway-dir.js';
import type { RdcConfig } from '../../types/index.js';

const { server, secureMem, relay, account, pushSpy, messages, active } = vi.hoisted(() => ({
  /** The config server's side: what it holds, and which credentials open it. */
  server: {
    storeId: '',
    configId: '',
    version: 0,
    config: {},
    slotSecrets: new Set<string>(),
    wrappedCek: '',
    failure: null as (() => Error) | null,
  },
  secureMem: new Map<string, string>(),
  relay: { payload: null as Record<string, unknown> | null, runs: 0 },
  account: { enroll: null as Record<string, unknown> | null, enrollCalls: 0 },
  pushSpy: vi.fn(),
  messages: [] as string[],
  active: { name: '' },
}));

vi.mock('../../utils/secure-storage.js', () => ({
  getSecureStorage: () => ({
    type: 'mem',
    get: (k: string) => Promise.resolve(secureMem.get(k) ?? null),
    set: (k: string, v: string) => {
      secureMem.set(k, v);
      return Promise.resolve();
    },
    delete: (k: string) => {
      secureMem.delete(k);
      return Promise.resolve();
    },
  }),
}));

vi.mock('../../adapters/remote-config-adapter.js', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../adapters/remote-config-adapter.js')>();
  const { ConfigServerError } = await import('../../services/config/config-server-client.js');
  type Storage = { get(key: string): Promise<string | null> };
  type Tokens = { get(name: string): Promise<{ token?: string; wrappedCek?: string } | null> };
  class FakeServerAdapter {
    constructor(
      private readonly remote: { storeId: string; configId: string; storageKeyId: string },
      private readonly configName: string,
      private readonly tokens: Tokens,
      private readonly secure: Storage
    ) {}

    /** The real adapter's order: the token, the request, then the slot secret and the unwrap. */
    async pull() {
      const token = await this.tokens.get(this.configName);
      if (!token?.token) throw new original.RemoteTokenExpiredError();
      this.request();
      await this.unwrap(token.wrappedCek);
      return { config: structuredClone(server.config), version: server.version, sdkEpoch: 1 };
    }

    private request(): void {
      if (server.failure) throw server.failure();
      if (this.remote.storeId !== server.storeId || this.remote.configId !== server.configId) {
        throw new ConfigServerError('Config not found', 404);
      }
    }

    private async unwrap(wrappedCek: string | undefined): Promise<void> {
      const secret = await this.secure.get(this.remote.storageKeyId);
      if (!secret) throw new original.RemotePasskeySecretMissingError();
      if (!server.slotSecrets.has(secret) || wrappedCek !== server.wrappedCek) {
        throw new original.RemoteStaleSlotError();
      }
    }

    push = pushSpy;
  }
  return { ...original, RemoteConfigAdapter: FakeServerAdapter };
});

vi.mock('../config-remote-relay.js', () => ({
  tryOpenBrowser: vi.fn(),
  runRelayHandoff: () => {
    relay.runs += 1;
    if (!relay.payload) return Promise.reject(new Error('the test armed no relay handoff'));
    return Promise.resolve(relay.payload);
  },
}));

vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: (path: string) => {
    if (path.endsWith('/configs/enable-requirements')) {
      return Promise.resolve({
        email: 'op@example.com',
        totpEnabled: true,
        configServiceAvailable: true,
      });
    }
    if (path.endsWith('/configs/password-enroll')) {
      account.enrollCalls += 1;
      if (!account.enroll) return Promise.reject(new Error('the test armed no password slot'));
      return Promise.resolve(account.enroll);
    }
    return Promise.reject(new Error(`unexpected account request: ${path}`));
  },
}));

vi.mock('../../services/account/subscription-auth.js', async (importOriginal) => {
  const original =
    await importOriginal<typeof import('../../services/account/subscription-auth.js')>();
  return {
    ...original,
    getSubscriptionServerUrl: () => 'https://account.test',
    getSubscriptionTokenState: () => ({
      kind: 'ready',
      serverUrl: 'https://account.test',
      token: { token: 'login-token' },
    }),
  };
});

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getEffectiveConfigName: () => active.name,
    getCurrentName: () => active.name,
    setRuntimeConfig: vi.fn(),
  },
}));

vi.mock('../../services/core/output.js', () => {
  const record = (text: string) => {
    messages.push(text);
  };
  return {
    outputService: { success: record, info: record, warn: record, error: record, print: vi.fn() },
  };
});

vi.mock('../../utils/spinner.js', () => ({
  withSpinner: <T>(_text: string, fn: () => Promise<T>) => fn(),
  stopSpinner: vi.fn(),
}));

// A refused command reaches the test as the error it raised, not as a process exit.
vi.mock('../../utils/errors.js', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../utils/errors.js')>();
  return {
    ...original,
    handleError: (error: unknown) => {
      throw error;
    },
  };
});

import {
  derivePasswordSlotSecret,
  newPasswordSlotParams,
  toBase64,
} from '@rediacc/shared/config-crypto';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import {
  RemotePasskeySecretMissingError,
  RemoteRollbackError,
  RemoteUnreachableError,
} from '../../adapters/remote-config-adapter.js';
import { remoteTokenStorage } from '../../adapters/remote-token-storage.js';
import { RemoteTokenRefreshError } from '../../services/config/device-token-refresh.js';
import { registerRemoteCommands } from '../config-remote.js';

// ─── Fixtures ────────────────────────────────────────────────────────────

const API_URL = 'https://account.test';
const STORE_ID = '11111111-1111-4111-8111-111111111111';
const OTHER_STORE_ID = '99999999-9999-4999-8999-999999999999';
const CONFIG_ID = '22222222-2222-4222-8222-222222222222';
const OTHER_CONFIG_ID = '44444444-4444-4444-8444-444444444444';
const PASSKEY_KEY_ID = 'rdc:pk:02cb65bf-0000-4000-8000-000000000001';
const SLOT_SECRET = 'c2xvdC1zZWNyZXQ';
const WRAPPED_CEK = 'wrapped-cek-g1';

let sequence = 0;

/** The linked config's cache file as the last pull left it at server version 5, host-local sections included. */
function linkedCache(): Record<string, unknown> {
  return {
    schemaVersion: 3,
    id: CONFIG_ID,
    version: 9,
    remote: {
      apiUrl: API_URL,
      storeId: STORE_ID,
      configId: CONFIG_ID,
      storageKeyId: PASSKEY_KEY_ID,
      cachedVersion: 5,
      cachedAt: '2026-09-26T10:00:00.000Z',
    },
    encryption: { mode: 'plaintext' },
    renetPath: '/opt/dev/renet',
    account: { accountServer: API_URL, e2ePublicKey: 'device-synced-key' },
    machines: { m1: { ip: '10.0.0.1', user: 'root' } },
    state: { repos: { mail: { latest: { networkId: 2816 } } } },
    fromANewerCli: { keep: true },
  };
}

/** What the server holds: version 7, with a machine another device added after this device's last pull. */
function serverCopy(): Record<string, unknown> {
  return {
    schemaVersion: 3,
    id: CONFIG_ID,
    version: 7,
    encryption: { mode: 'plaintext' },
    machines: { m1: { ip: '10.0.0.1', user: 'root' }, m2: { ip: '10.0.0.2', user: 'root' } },
  };
}

function handoff(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    passkey_secret: SLOT_SECRET,
    token: 'rct_fresh',
    storageKeyId: PASSKEY_KEY_ID,
    wrappedCek: WRAPPED_CEK,
    storeId: STORE_ID,
    apiUrl: API_URL,
    configId: CONFIG_ID,
    handoffNonce: 'nonce-1',
    ...overrides,
  };
}

async function writeConfigFile(doc: Record<string, unknown>): Promise<void> {
  await fs.mkdir(configFileStorage.getConfigDir(), { recursive: true });
  await fs.writeFile(configFileStorage.getConfigPath(active.name), JSON.stringify(doc, null, 2));
  configFileStorage.clearCache();
}

async function readConfigFile(): Promise<Record<string, unknown> & RdcConfig> {
  const raw = await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8');
  return JSON.parse(raw) as Record<string, unknown> & RdcConfig;
}

/** A device that was enrolled and working: the cache file, the token file, the slot secret. */
async function enrolledDevice(): Promise<void> {
  await writeConfigFile(linkedCache());
  await remoteTokenStorage.set(active.name, {
    token: 'rct_before',
    wrappedCek: WRAPPED_CEK,
    sync: {
      binding: `${STORE_ID}/${CONFIG_ID}/`,
      highWater: 5,
      envelopeVersion: 3,
      fckSalt: 'salt',
    },
  });
  secureMem.set(PASSKEY_KEY_ID, SLOT_SECRET);
}

/** The reboot: the kernel keyring is empty again, everything on disk is as it was. */
function reboot(): void {
  secureMem.clear();
}

async function rdc(...args: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerRemoteCommands(program);
  await program.parseAsync(['node', 'rdc', 'remote', ...args]);
}

async function refusal(...args: string[]): Promise<Error> {
  const error = await rdc(...args).then(
    () => undefined,
    (e: unknown) => e
  );
  if (!(error instanceof Error))
    throw new Error(`rdc config remote ${args.join(' ')} did not fail`);
  return error;
}

beforeEach(async () => {
  // One local config per test: a slot secret is shared by every local config that names its key id (F17), so a
  // leftover file of an earlier test would keep the secret alive through a cleanup.
  assertThrowawayDir(configFileStorage.getConfigDir());
  await fs.rm(configFileStorage.getConfigDir(), { recursive: true, force: true });
  configFileStorage.clearCache();
  sequence += 1;
  active.name = `reenroll-${sequence}`;
  secureMem.clear();
  messages.length = 0;
  pushSpy.mockReset();
  relay.payload = null;
  relay.runs = 0;
  account.enroll = null;
  account.enrollCalls = 0;
  delete process.env.REDIACC_STORE_MASTER_PASSWORD;
  Object.assign(server, {
    storeId: STORE_ID,
    configId: CONFIG_ID,
    version: 7,
    config: serverCopy(),
    slotSecrets: new Set([SLOT_SECRET]),
    wrappedCek: WRAPPED_CEK,
    failure: null,
  });
});

// ─── Controls: what must hold with or without the re-enrollment ──────────

describe('config remote enable on a linked config: controls', () => {
  it('reads through a working enrollment (the harness answers like the server)', async () => {
    await enrolledDevice();
    await rdc('refresh');
    expect((await readConfigFile()).remote).toMatchObject({
      configId: CONFIG_ID,
      cachedVersion: 7,
    });
  });

  it('loses every read once the keyring is empty, with the slot-secret error', async () => {
    await enrolledDevice();
    reboot();
    expect(await refusal('refresh')).toBeInstanceOf(RemotePasskeySecretMissingError);
  });

  it('still refuses while the enrollment works, and the command the refusal names then succeeds', async () => {
    await enrolledDevice();
    relay.payload = handoff();

    const error = await refusal('enable');

    expect(relay.runs).toBe(0);
    expect(account.enrollCalls).toBe(0);
    const named = /rdc config remote (\w+)/.exec(error.message)?.[1];
    expect(named).toBe('disable');
    await rdc(named as string);
    expect((await readConfigFile()).remote).toBeUndefined();
  });
});

// ─── The way back ────────────────────────────────────────────────────────

describe('config remote enable on a linked config whose slot secret is gone', () => {
  it('enrolls this device again for the same store, and the next pull succeeds', async () => {
    await enrolledDevice();
    reboot();
    relay.payload = handoff();

    await rdc('enable');

    expect(relay.runs).toBe(1);
    expect(secureMem.get(PASSKEY_KEY_ID)).toBe(SLOT_SECRET);
    expect(await remoteTokenStorage.get(active.name)).toMatchObject({
      token: 'rct_fresh',
      wrappedCek: WRAPPED_CEK,
    });
    expect((await readConfigFile()).remote).toMatchObject({
      apiUrl: API_URL,
      storeId: STORE_ID,
      configId: CONFIG_ID,
      storageKeyId: PASSKEY_KEY_ID,
    });

    // A following pull, through a different command, with the stored credentials alone.
    relay.payload = null;
    await rdc('refresh');
    expect((await readConfigFile()).remote).toMatchObject({
      storeId: STORE_ID,
      configId: CONFIG_ID,
    });
  });

  it('the slot-secret error names a command, and running that command recovers the config', async () => {
    await enrolledDevice();
    reboot();
    relay.payload = handoff();

    const error = await refusal('refresh');
    const named = /rdc config remote (\w+)/.exec(error.message)?.[1];
    expect(named).toBeDefined();

    await rdc(named as string);
    await rdc('refresh');
    expect(secureMem.has(PASSKEY_KEY_ID)).toBe(true);
  });

  it('takes the newer server content, never pushes, and keeps every host-local section', async () => {
    await enrolledDevice();
    reboot();
    relay.payload = handoff();

    await rdc('enable');
    const written = await readConfigFile();

    // Another device's write (m2, server version 7) arrives; nothing of this device overwrote it.
    expect(pushSpy).not.toHaveBeenCalled();
    expect(server.version).toBe(7);
    expect(written.machines).toHaveProperty('m2');
    expect(written.remote).toMatchObject({ cachedVersion: 7 });
    // Host-local sections come from the local copy; the pull carries none of them.
    expect(written.renetPath).toBe('/opt/dev/renet');
    expect(written.encryption).toEqual({ mode: 'plaintext' });
    expect(written.account).toMatchObject({
      accountServer: API_URL,
      e2ePublicKey: 'device-synced-key',
    });
    expect(written.state).toEqual({ repos: { mail: { latest: { networkId: 2816 } } } });
    expect(written.fromANewerCli).toEqual({ keep: true });
    // A cache write is an observation: the device-local version counter does not move.
    expect(written.version).toBe(9);
    // The token file kept what this device had already seen of the config.
    expect((await remoteTokenStorage.get(active.name))?.sync).toMatchObject({ highWater: 5 });
  });

  it('refuses a server copy older than the cache and puts the device back as it was', async () => {
    await enrolledDevice();
    reboot();
    relay.payload = handoff();
    server.version = 3;
    const before = await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8');

    expect(await refusal('enable')).toBeInstanceOf(RemoteRollbackError);

    expect(await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8')).toBe(before);
    expect(secureMem.size).toBe(0);
    expect(await remoteTokenStorage.get(active.name)).toMatchObject({ token: 'rct_before' });
  });

  it('refuses credentials for another store, and for another config of the same store', async () => {
    await enrolledDevice();
    reboot();
    const before = await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8');

    relay.payload = handoff({ storeId: OTHER_STORE_ID });
    expect((await refusal('enable')).message).toContain(OTHER_STORE_ID);

    relay.payload = handoff({ configId: OTHER_CONFIG_ID });
    expect((await refusal('enable')).message).toContain(OTHER_CONFIG_ID);

    expect(await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8')).toBe(before);
    expect(secureMem.size).toBe(0);
    expect(await remoteTokenStorage.get(active.name)).toMatchObject({ token: 'rct_before' });
  });

  it('names a store that no longer holds the config instead of seeding it from the cache', async () => {
    await enrolledDevice();
    reboot();
    relay.payload = handoff({ configId: undefined });
    server.configId = OTHER_CONFIG_ID;

    const error = await refusal('enable');
    expect(error.message).toContain(CONFIG_ID);
    expect(error.message).toContain('rdc config remote disable --local');
    expect(pushSpy).not.toHaveBeenCalled();
    expect(secureMem.size).toBe(0);
  });

  it('refuses --api-url for another server than the one the config is linked to', async () => {
    await enrolledDevice();
    reboot();
    relay.payload = handoff();

    expect((await refusal('enable', '--api-url', 'https://elsewhere.test')).message).toContain(
      'https://elsewhere.test'
    );
    expect(relay.runs).toBe(0);
  });
});

describe('config remote enable --master-password on a linked config whose slot secret is gone', () => {
  const PASSWORD = 'correct horse battery staple';

  async function passwordSlot(): Promise<void> {
    const kdfParams = newPasswordSlotParams();
    server.slotSecrets.add(toBase64(await derivePasswordSlotSecret(PASSWORD, kdfParams)));
    account.enroll = {
      method: 'password',
      kdfParams,
      wrappedCek: WRAPPED_CEK,
      token: 'rct_password',
      storeId: STORE_ID,
      configId: CONFIG_ID,
      teamId: null,
    };
  }

  it('enrolls again under a new key id, same store and config, and drops the old key id', async () => {
    await enrolledDevice();
    reboot();
    await passwordSlot();
    process.env.REDIACC_STORE_MASTER_PASSWORD = PASSWORD;

    await rdc('enable', '--master-password');

    const pointer = (await readConfigFile()).remote;
    expect(pointer).toMatchObject({ storeId: STORE_ID, configId: CONFIG_ID, cachedVersion: 7 });
    expect(pointer?.storageKeyId).toMatch(/^rdc:pw:/);
    expect([...secureMem.keys()]).toEqual([pointer?.storageKeyId]);
    await rdc('refresh');
  });

  it('refuses --config-id naming another config than the linked one, before any enrollment', async () => {
    await enrolledDevice();
    reboot();
    await passwordSlot();
    process.env.REDIACC_STORE_MASTER_PASSWORD = PASSWORD;
    const before = await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8');

    const error = await refusal(
      'enable',
      '--master-password',
      '--config-id',
      'someone-elses-config'
    );

    expect(error.message).toContain('someone-elses-config');
    expect(error.message).toContain(CONFIG_ID);
    expect(account.enrollCalls).toBe(0);
    expect(await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8')).toBe(before);
  });

  it('accepts --config-id naming the linked config and re-enrolls', async () => {
    await enrolledDevice();
    reboot();
    await passwordSlot();
    process.env.REDIACC_STORE_MASTER_PASSWORD = PASSWORD;

    await rdc('enable', '--master-password', '--config-id', CONFIG_ID);

    expect(account.enrollCalls).toBe(1);
    expect((await readConfigFile()).remote?.storageKeyId).toMatch(/^rdc:pw:/);
  });

  it('reports a wrong password and leaves the device as it was', async () => {
    await enrolledDevice();
    reboot();
    await passwordSlot();
    process.env.REDIACC_STORE_MASTER_PASSWORD = 'not the password';
    const before = await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8');

    expect((await refusal('enable', '--master-password')).message).toMatch(/password/i);

    expect(await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8')).toBe(before);
    expect(secureMem.size).toBe(0);
    expect(await remoteTokenStorage.get(active.name)).toMatchObject({ token: 'rct_before' });
  });
});

describe('config remote enable on a linked config: other lost and not-lost enrollments', () => {
  it('enrolls again when the token file is gone', async () => {
    await enrolledDevice();
    await remoteTokenStorage.delete(active.name);
    relay.payload = handoff();

    await rdc('enable');
    await rdc('refresh');
  });

  it('enrolls again when the key was rotated away from this device', async () => {
    await enrolledDevice();
    server.wrappedCek = 'wrapped-cek-g2';
    relay.payload = handoff({ wrappedCek: 'wrapped-cek-g2' });

    await rdc('enable');
    await rdc('refresh');
    expect(await remoteTokenStorage.get(active.name)).toMatchObject({
      wrappedCek: 'wrapped-cek-g2',
    });
  });

  it('starts no enrollment while the server is unreachable', async () => {
    await enrolledDevice();
    server.failure = () => new RemoteUnreachableError(API_URL, new Error('ECONNREFUSED'));
    relay.payload = handoff();

    expect(await refusal('enable')).toBeInstanceOf(RemoteUnreachableError);
    expect(relay.runs).toBe(0);
  });

  it('starts no enrollment when the login belongs to an account outside the store', async () => {
    await enrolledDevice();
    server.failure = () => new RemoteTokenRefreshError('not_store_member', 'not a member');
    relay.payload = handoff();

    expect(await refusal('enable')).toBeInstanceOf(RemoteTokenRefreshError);
    expect(relay.runs).toBe(0);
  });

  // Review 0021d122.2: the cured set is closed. A renewal that failed for a reason nobody listed says nothing about this device's credentials, and must not replace working ones.
  it.each([
    'refresh_failed',
    'malformed_response',
    'a_code_no_release_knows',
    'rate_limited',
    'login_invalid',
    'login_scope',
    'store_mismatch',
  ])('starts no enrollment on the renewal refusal %s, and raises it as it came', async (code) => {
    await enrolledDevice();
    const before = await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8');
    server.failure = () => new RemoteTokenRefreshError(code, `renewal refused: ${code}`);
    relay.payload = handoff();

    const error = await refusal('enable');
    expect(error).toBeInstanceOf(RemoteTokenRefreshError);
    expect((error as RemoteTokenRefreshError).code).toBe(code);
    expect(relay.runs).toBe(0);
    expect(await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8')).toBe(before);
    expect(await remoteTokenStorage.get(active.name)).toMatchObject({ token: 'rct_before' });
    expect(secureMem.get(PASSKEY_KEY_ID)).toBe(SLOT_SECRET);
  });

  it.each(['stale_cek_generation', 'login_ip_mismatch'])(
    'enrolls again on the renewal refusal %s, which a new enrollment cures',
    async (code) => {
      await enrolledDevice();
      // The renewal is refused once, for the probe's pull; the enrollment's own pull then reaches the server.
      server.failure = () => {
        server.failure = null;
        return new RemoteTokenRefreshError(code, `renewal refused: ${code}`);
      };
      relay.payload = handoff();

      await rdc('enable');

      expect(relay.runs).toBe(1);
      expect(await remoteTokenStorage.get(active.name)).toMatchObject({ token: 'rct_fresh' });
    }
  );

  // Review 0021d122.1: the credentials work and the store answers 404. No enrollment brings the config back, so the probe names the way out instead of a raw "Config not found".
  it('names the local-only unlink when the credentials work and the store no longer holds the config', async () => {
    await enrolledDevice();
    const before = await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8');
    server.configId = OTHER_CONFIG_ID;
    relay.payload = handoff();

    const error = await refusal('enable');
    expect(error.message).toContain('rdc config remote disable --local');
    expect(error.message).toContain(CONFIG_ID);
    expect(error.message).toContain(STORE_ID);
    expect(error.message).not.toBe('Config not found');
    expect(relay.runs).toBe(0);
    expect(await fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8')).toBe(before);
    expect(secureMem.get(PASSKEY_KEY_ID)).toBe(SLOT_SECRET);
  });
});
