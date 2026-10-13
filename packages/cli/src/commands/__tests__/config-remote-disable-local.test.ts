/**
 * `rdc config remote disable --local`, and where the server-backed commands name it.
 *
 * The dead end this file pins (operator ruling 2026-10-13): `disable` is server-only, so a linked
 * config whose store copy is gone, or whose account left the store, could never be unlinked. The
 * local-only unlink drops the link and keeps the copy this device cached, after a confirmation
 * that says newer server data is not fetched. `disable` without `--local` stays server-only.
 *
 * Real here: the config file storage and the token file storage (both in the throwaway config home
 * of isolate-config-home.ts), the cache merge, master-password encryption at rest, the command
 * registration, and both disable flows. Faked: the OS secure storage (an in-memory map; a test
 * must never touch a real keyring), the confirmation prompt, the portal relay, and the adapter,
 * which answers the way the config server would for the state a test arms.
 */

import { promises as fs } from 'node:fs';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RdcConfig } from '../../types/index.js';

interface FakeServer {
  config: unknown;
  version: number;
  failure: (() => Error) | null;
}

const { server, secureMem, secureDown, prompt, relay, messages, active } = vi.hoisted(() => {
  /** The config server's side: the copy it holds, or the failure it answers every pull with. */
  const server: FakeServer = { config: {}, version: 0, failure: null };
  return {
    server,
    secureMem: new Map<string, string>(),
    /** When set, this device has no usable secure storage: selection throws the typed refusal. */
    secureDown: { message: null as string | null },
    prompt: { answer: false, asked: [] as string[] },
    relay: { runs: 0 },
    messages: [] as string[],
    active: { name: '' },
  };
});

vi.mock('../../utils/secure-storage.js', () => {
  class SecureStorageUnavailableError extends Error {}
  return {
    SecureStorageUnavailableError,
    getSecureStorage: () => {
      if (secureDown.message !== null) throw new SecureStorageUnavailableError(secureDown.message);
      return {
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
      };
    },
  };
});

vi.mock('../../adapters/remote-config-adapter.js', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../adapters/remote-config-adapter.js')>();
  class FakeServerAdapter {
    pull() {
      if (server.failure) return Promise.reject(server.failure());
      return Promise.resolve({
        config: structuredClone(server.config),
        version: server.version,
        sdkEpoch: 1,
      });
    }
  }
  return { ...original, RemoteConfigAdapter: FakeServerAdapter };
});

// The real askConfirm answers yes without asking when REDIACC_YES=1; the fake keeps that, and records every question it is really asked.
vi.mock('../../utils/prompt.js', () => ({
  askConfirm: (message: string) => {
    if (process.env.REDIACC_YES === '1') return Promise.resolve(true);
    prompt.asked.push(message);
    return Promise.resolve(prompt.answer);
  },
}));

vi.mock('../config-remote-relay.js', () => ({
  tryOpenBrowser: vi.fn(),
  runRelayHandoff: () => {
    relay.runs += 1;
    return Promise.reject(new Error('no test here approves a handoff'));
  },
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getEffectiveConfigName: () => active.name },
}));

vi.mock('../../services/core/output.js', () => {
  const record = (text: string) => {
    messages.push(text);
  };
  return {
    outputService: { success: record, info: record, warn: record, error: record, print: vi.fn() },
  };
});

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

import { configFileStorage } from '../../adapters/config-file-storage.js';
import {
  RemoteTeamForbiddenError,
  RemoteUnreachableError,
} from '../../adapters/remote-config-adapter.js';
import { remoteTokenStorage } from '../../adapters/remote-token-storage.js';
import { ConfigServerError } from '../../services/config/config-server-client.js';
import { RemoteTokenRefreshError } from '../../services/config/device-token-refresh.js';
import { mergeRemoteIntoCache } from '../../services/config/remote-cache.js';
import { registerRemoteCommands } from '../config-remote.js';

// ─── Fixtures ────────────────────────────────────────────────────────────

const API_URL = 'https://account.test';
const STORE_ID = '11111111-1111-4111-8111-111111111111';
const CONFIG_ID = '22222222-2222-4222-8222-222222222222';
const KEY_ID = 'rdc:pk:02cb65bf-0000-4000-8000-000000000001';
const UNLINK = 'rdc config remote disable --local';

let sequence = 0;

/** What the store held at version 5, the last time this device pulled. */
function pulledAtV5(): RdcConfig {
  return {
    schemaVersion: 3,
    id: CONFIG_ID,
    version: 5,
    encryption: { mode: 'plaintext' },
    defaults: { language: 'en', universalUser: 'rediacc' },
    machines: { m1: { ip: '10.0.0.1', user: 'root' } },
  } as unknown as RdcConfig;
}

/** This device's own half of the file: the pointer and every host-local section a pull never carries. */
function deviceHalf(): RdcConfig {
  return {
    schemaVersion: 3,
    id: CONFIG_ID,
    version: 9,
    remote: { apiUrl: API_URL, storeId: STORE_ID, configId: CONFIG_ID, storageKeyId: KEY_ID },
    encryption: { mode: 'plaintext' },
    renetPath: '/opt/dev/renet',
    account: { accountServer: API_URL, e2ePublicKey: 'device-synced-key' },
    credentials: { masterPasswordVerifier: 'mpv-hash' },
    state: { repos: { mail: { latest: { networkId: 2816 } } } },
    fromANewerCli: { keep: true },
  } as unknown as RdcConfig;
}

/** The linked config's file as the pull of version 5 left it, written by the one cache merge. */
function linkedCache(): RdcConfig {
  return mergeRemoteIntoCache(deviceHalf(), pulledAtV5(), 5);
}

/** The same content as a config that was never linked. */
function unlinkedConfig(): RdcConfig {
  const local = linkedCache();
  delete local.remote;
  return local;
}

async function writeConfigFile(doc: unknown, name = active.name): Promise<void> {
  await fs.mkdir(configFileStorage.getConfigDir(), { recursive: true });
  await fs.writeFile(configFileStorage.getConfigPath(name), JSON.stringify(doc, null, 2));
  configFileStorage.clearCache();
}

function fileBytes(): Promise<string> {
  return fs.readFile(configFileStorage.getConfigPath(active.name), 'utf-8');
}

async function readConfigFile(): Promise<Record<string, unknown> & RdcConfig> {
  return JSON.parse(await fileBytes()) as Record<string, unknown> & RdcConfig;
}

/** A linked device with its cache, its token file and its slot secret. */
async function linkedDevice(doc: unknown = linkedCache()): Promise<void> {
  await writeConfigFile(doc);
  await remoteTokenStorage.set(active.name, { token: 'rct_before', wrappedCek: 'wrapped-cek' });
  secureMem.set(KEY_ID, 'slot-secret');
}

/** The device still holds everything it held: the file byte for byte, the token file, the slot secret. */
async function expectUntouched(before: string): Promise<void> {
  expect(await fileBytes()).toBe(before);
  expect(await remoteTokenStorage.get(active.name)).toMatchObject({ token: 'rct_before' });
  expect(secureMem.get(KEY_ID)).toBe('slot-secret');
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
  if (!(error instanceof Error)) {
    throw new Error(`rdc config remote ${args.join(' ')} did not fail`);
  }
  return error;
}

const gone = () => new ConfigServerError('Config not found', 404);

beforeEach(async () => {
  await fs.rm(configFileStorage.getConfigDir(), { recursive: true, force: true });
  configFileStorage.clearCache();
  sequence += 1;
  active.name = `unlink-${sequence}`;
  secureMem.clear();
  secureDown.message = null;
  prompt.answer = false;
  prompt.asked.length = 0;
  relay.runs = 0;
  messages.length = 0;
  Object.assign(server, { config: pulledAtV5(), version: 5, failure: null });
});

const STDIN_WAS_TTY = process.stdin.isTTY;

/** Whether stdin is a terminal for the command under test: the prompt is only reached on one. */
function setTerminal(isTTY: boolean | undefined): void {
  Object.defineProperty(process.stdin, 'isTTY', { value: isTTY, configurable: true });
}

afterEach(() => {
  delete process.env.REDIACC_MASTER_PASSWORD;
  delete process.env.REDIACC_YES;
  setTerminal(STDIN_WAS_TTY);
});

// ─── Controls: the server-backed disable is unchanged ────────────────────

describe('config remote disable with a healthy server (control)', () => {
  it('pulls, writes the server copy with every host-local section, and asks nothing', async () => {
    await linkedDevice();
    server.config = { ...pulledAtV5(), machines: { m2: { ip: '10.0.0.2', user: 'root' } } };
    server.version = 6;

    await rdc('disable');

    const written = await readConfigFile();
    expect(written.remote).toBeUndefined();
    // The newer server copy, not the cached one.
    expect(written.machines).toEqual({ m2: { ip: '10.0.0.2', user: 'root' } });
    expect(written.renetPath).toBe('/opt/dev/renet');
    expect(written.state).toEqual({ repos: { mail: { latest: { networkId: 2816 } } } });
    expect(written.fromANewerCli).toEqual({ keep: true });
    expect(prompt.asked).toEqual([]);
    expect(await remoteTokenStorage.get(active.name)).toBeNull();
    expect(secureMem.size).toBe(0);
  });

  it('an unreachable server is still refused as "retry later", and that refusal does not offer the unlink', async () => {
    await linkedDevice();
    const before = await fileBytes();
    server.failure = () => new RemoteUnreachableError(API_URL, new Error('ECONNREFUSED'));

    const error = await refusal('disable');
    expect(error.message).toContain(API_URL);
    expect(error.message).not.toContain('--local');
    await expectUntouched(before);
  });

  it('a team refusal is raised as it came and does not offer the unlink (the read path removes that cache)', async () => {
    await linkedDevice();
    const before = await fileBytes();
    server.failure = () => new RemoteTeamForbiddenError(active.name);

    const error = await refusal('disable');
    expect(error).toBeInstanceOf(RemoteTeamForbiddenError);
    expect(error.message).not.toContain('--local');
    await expectUntouched(before);
  });
});

// ─── The closed server path names the unlink ─────────────────────────────

describe('config remote disable when the server path is closed for good', () => {
  const CLOSED: readonly (readonly [string, () => Error])[] = [
    ['the store no longer holds the config (404)', gone],
    ['the server forbids this account (403)', () => new ConfigServerError('Forbidden', 403)],
    [
      'the account left the store',
      () => new RemoteTokenRefreshError('not_store_member', 'not a member of the store'),
    ],
    [
      'the store belongs to another organization',
      () => new RemoteTokenRefreshError('store_mismatch', 'store of another organization'),
    ],
  ];

  it.each(CLOSED)(
    '%s: the refusal names the local-only unlink and changes nothing',
    async (_label, failure) => {
      await linkedDevice();
      const before = await fileBytes();
      server.failure = failure;

      const error = await refusal('disable');
      expect(error.message).toContain(UNLINK);
      expect(error.message).toContain(active.name);
      await expectUntouched(before);
    }
  );

  it('a renewal refusal that says nothing about the store is raised as it came', async () => {
    await linkedDevice();
    server.failure = () => new RemoteTokenRefreshError('rate_limited', 'slow down');

    const error = await refusal('disable');
    expect(error).toBeInstanceOf(RemoteTokenRefreshError);
    expect(error.message).not.toContain('--local');
  });
});

// ─── The local-only unlink ───────────────────────────────────────────────

describe('config remote disable --local', () => {
  it('writes what the server-backed disable writes when the server holds the cached version', async () => {
    // Control: the server-backed disable, against a server that still holds version 5.
    await linkedDevice();
    await rdc('disable');
    const viaServer = await readConfigFile();
    expect(viaServer.remote).toBeUndefined();

    // The same device, and a store that no longer holds the config.
    secureMem.clear();
    await linkedDevice();
    server.failure = gone;
    expect((await refusal('disable')).message).toContain(UNLINK);

    await rdc('disable', '--local', '--yes');

    const viaCache = await readConfigFile();
    expect(viaCache).toEqual(viaServer);
    expect(viaCache.remote).toBeUndefined();
    expect(viaCache.machines).toEqual({ m1: { ip: '10.0.0.1', user: 'root' } });
    expect(viaCache.renetPath).toBe('/opt/dev/renet');
    expect(viaCache.credentials?.masterPasswordVerifier).toBe('mpv-hash');
    expect(viaCache.state).toEqual({ repos: { mail: { latest: { networkId: 2816 } } } });
    expect(viaCache.fromANewerCli).toEqual({ keep: true });
    // This device's credentials for the config are gone.
    expect(await remoteTokenStorage.get(active.name)).toBeNull();
    expect(secureMem.size).toBe(0);
    // `--yes` answered the question, and the result still says what was not done.
    expect(prompt.asked).toEqual([]);
    expect(messages.join('\n')).toContain('was not fetched');
  });

  it('never asks the server: it works while every pull fails', async () => {
    await linkedDevice();
    server.failure = () => new Error('the unlink must not pull');
    await rdc('disable', '--local', '--yes');
    expect((await readConfigFile()).remote).toBeUndefined();
  });

  it('asks first, says newer server data is not fetched, and writes nothing when the answer is no', async () => {
    await linkedDevice();
    const before = await fileBytes();
    setTerminal(true);
    prompt.answer = false;

    await rdc('disable', '--local');

    expect(prompt.asked).toHaveLength(1);
    expect(prompt.asked[0]).toContain('is not fetched');
    expect(prompt.asked[0]).toContain(active.name);
    expect(prompt.asked[0]).toContain('version 5');
    await expectUntouched(before);
  });

  it('with no terminal and no --yes: refuses, says what --yes would confirm, asks nothing and writes nothing', async () => {
    await linkedDevice();
    const before = await fileBytes();
    setTerminal(undefined);

    const error = await refusal('disable', '--local');
    expect(error.message).toContain('does not fetch newer server data');
    expect(error.message).toContain('--yes');
    expect(prompt.asked).toEqual([]);
    await expectUntouched(before);

    // REDIACC_YES=1 confirms here as it does for every prompt of the CLI.
    process.env.REDIACC_YES = '1';
    await rdc('disable', '--local');
    expect((await readConfigFile()).remote).toBeUndefined();
    expect(prompt.asked).toEqual([]);
  });

  it('unlinks when the answer is yes', async () => {
    await linkedDevice();
    setTerminal(true);
    prompt.answer = true;

    await rdc('disable', '--local');

    expect(prompt.asked).toHaveLength(1);
    expect((await readConfigFile()).remote).toBeUndefined();
    expect(await remoteTokenStorage.get(active.name)).toBeNull();
  });

  it('refuses a pointer that holds no cached copy, names what is left, and leaves the file as it was', async () => {
    // The bare pointer of an enable that never reached its first pull, or of a cache the read path removed.
    await linkedDevice(deviceHalf());
    const before = await fileBytes();

    const error = await refusal('disable', '--local', '--yes');
    expect(error.message).toContain('no cached copy');
    expect(error.message).toContain(`rdc config delete ${active.name}`);
    await expectUntouched(before);
  });

  it('refuses a cache its master password cannot open, says what can be recovered, and leaves the file byte-identical', async () => {
    const SECRET = 'cf-token-kept-encrypted-at-rest';
    process.env.REDIACC_MASTER_PASSWORD = 'the-right-password';
    const cache = linkedCache();
    await configFileStorage.save(
      {
        ...cache,
        encryption: { mode: 'master-password' },
        credentials: { ...cache.credentials, cfDnsApiToken: SECRET },
      },
      active.name
    );
    await remoteTokenStorage.set(active.name, { token: 'rct_before', wrappedCek: 'wrapped-cek' });
    secureMem.set(KEY_ID, 'slot-secret');
    const before = await fileBytes();
    // Control: the secret is encrypted at rest, and the right password opens it.
    expect(before).not.toContain(SECRET);
    expect((await configFileStorage.loadDecrypted(active.name)).credentials?.cfDnsApiToken).toBe(
      SECRET
    );

    process.env.REDIACC_MASTER_PASSWORD = 'not-the-password';
    configFileStorage.clearCache();
    const error = await refusal('disable', '--local', '--yes');
    expect(error.message).toContain('REDIACC_MASTER_PASSWORD');
    expect(error.message).toContain('version 5');
    await expectUntouched(before);

    // With the password the same cache unlinks whole, and the secret stays encrypted at rest.
    process.env.REDIACC_MASTER_PASSWORD = 'the-right-password';
    configFileStorage.clearCache();
    await rdc('disable', '--local', '--yes');
    expect(await fileBytes()).not.toContain(SECRET);
    configFileStorage.clearCache();
    const unlinked = await configFileStorage.loadDecrypted(active.name);
    expect(unlinked.remote).toBeUndefined();
    expect(unlinked.credentials?.cfDnsApiToken).toBe(SECRET);
    expect(unlinked.machines).toEqual({ m1: { ip: '10.0.0.1', user: 'root' } });
  });

  it('keeps the slot secret another local config is enrolled with', async () => {
    await linkedDevice();
    await writeConfigFile(linkedCache(), 'second');

    await rdc('disable', '--local', '--yes');

    expect(await remoteTokenStorage.get(active.name)).toBeNull();
    expect(secureMem.get(KEY_ID)).toBe('slot-secret');
  });

  it('still unlinks on a device with no usable secure storage, and says the key was not removed', async () => {
    await linkedDevice();
    secureDown.message = '`keyctl` is not installed';

    await rdc('disable', '--local', '--yes');

    expect((await readConfigFile()).remote).toBeUndefined();
    expect(await remoteTokenStorage.get(active.name)).toBeNull();
    expect(messages.join('\n')).toContain('`keyctl` is not installed');
  });

  it('refuses a config that is not linked', async () => {
    await writeConfigFile(unlinkedConfig());
    const before = await fileBytes();

    await expect(rdc('disable', '--local', '--yes')).rejects.toThrow(/not enabled/);
    expect(await fileBytes()).toBe(before);
  });
});

// ─── No secure storage: refused before any ceremony ──────────────────────

describe('config remote on a device with no usable secure storage', () => {
  it('enable refuses before any portal link is produced', async () => {
    await writeConfigFile(unlinkedConfig());
    secureDown.message = 'set REDIACC_SECRET_STORE=file';

    const error = await refusal('enable');
    expect(error.message).toContain('REDIACC_SECRET_STORE=file');
    expect(relay.runs).toBe(0);
  });

  it('status reports the refusal instead of a bare "error"', async () => {
    await linkedDevice();
    secureDown.message = 'set REDIACC_SECRET_STORE=file';

    expect((await refusal('status')).message).toContain('REDIACC_SECRET_STORE=file');
  });

  it('the server-backed disable refuses with the same guidance and changes nothing', async () => {
    await linkedDevice();
    const before = await fileBytes();
    secureDown.message = 'set REDIACC_SECRET_STORE=file';

    expect((await refusal('disable')).message).toContain('REDIACC_SECRET_STORE=file');
    expect(await fileBytes()).toBe(before);
  });
});
