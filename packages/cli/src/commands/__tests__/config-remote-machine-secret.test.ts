/**
 * Headless enrollment by a machine secret (`rdc config remote enable --machine-secret <id>`, D46).
 *
 * The crypto is REAL: a genuine machine secret wraps a real CEK (HKDF-derived wrapping secret +
 * serverSecret), a genuine encrypted config stands behind the probe pull, and the enroll flow
 * unwraps it end to end. Only the I/O seams (account API, config API, OS secure storage, config
 * and token files, stdin) are mocked.
 *
 * The secret never comes from argv: the option takes the secret's id, and the secret itself is
 * read from REDIACC_MACHINE_SECRET or stdin.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockAccountServerFetch,
  mockConfigServerFetch,
  mockReadStdinValue,
  mockAskPassword,
  secureMem,
  tokenMem,
  mockConfigFileStorage,
} = vi.hoisted(() => ({
  mockAccountServerFetch: vi.fn(),
  mockConfigServerFetch: vi.fn(),
  mockReadStdinValue: vi.fn(),
  mockAskPassword: vi.fn(),
  secureMem: new Map<string, string>(),
  tokenMem: new Map<string, { token: string; wrappedCek: string }>(),
  mockConfigFileStorage: {
    list: vi.fn(() => Promise.resolve([] as string[])),
    load: vi.fn(),
    loadDecrypted: vi.fn(),
    save: vi.fn(),
    getConfigPath: vi.fn(),
    // config-remote.ts wires the remote state writer when it loads.
    setRemoteStateWriter: vi.fn(),
  },
}));

vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: mockAccountServerFetch,
}));

vi.mock('../../utils/stdin.js', () => ({ readStdinValue: mockReadStdinValue }));

// The TTY branch asks here; stubbed so no run ever opens a real prompt.
vi.mock('../../utils/prompt.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/prompt.js')>()),
  askPassword: mockAskPassword,
}));

vi.mock('../../services/config/config-server-client.js', () => ({
  configServerFetch: mockConfigServerFetch,
  ConfigServerError: class ConfigServerError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.name = 'ConfigServerError';
      this.status = status;
    }
  },
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

vi.mock('../../adapters/remote-token-storage.js', () => ({
  remoteTokenStorage: {
    get: (name: string) => Promise.resolve(tokenMem.get(name) ?? null),
    recordEnrollment: () => Promise.resolve(),
    set: (name: string, data: { token: string; wrappedCek: string }) => {
      tokenMem.set(name, data);
      return Promise.resolve();
    },
    updateToken: (name: string, token: string) => {
      const cur = tokenMem.get(name);
      if (cur) tokenMem.set(name, { ...cur, token });
      return Promise.resolve();
    },
    withLease: <T>(name: string, fn: (lease: unknown) => Promise<T>) => {
      const data = tokenMem.get(name) ?? null;
      return fn({
        data,
        get token() {
          return tokenMem.get(name)?.token;
        },
        get sync() {
          return (tokenMem.get(name) as { sync?: unknown } | undefined)?.sync;
        },
        update: (token: string) => {
          const cur = tokenMem.get(name);
          if (cur) tokenMem.set(name, { ...cur, token });
          return Promise.resolve();
        },
        recordSync: (sync: unknown) => {
          const cur = tokenMem.get(name);
          if (cur) tokenMem.set(name, { ...cur, sync } as typeof cur);
          return Promise.resolve();
        },
      });
    },
    delete: (name: string) => {
      tokenMem.delete(name);
      return Promise.resolve();
    },
  },
}));

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: mockConfigFileStorage,
}));

import {
  deriveMachineSecretSlotSecret,
  generateCek,
  generateMachineSecret,
  generateServerSecret,
  importAesKey,
  newMachineSecretParams,
  randomBytes,
  toBase64,
  wrapCekForSlot,
} from '@rediacc/shared/config-crypto';
import { buildConfigPushPayload } from '@rediacc/shared/config-schema';
import { RemoteStaleSlotError } from '../../adapters/remote-config-adapter.js';
import type { RdcConfig } from '../../types/index.js';
import { registerRemoteCommands } from '../config-remote.js';
import {
  enableMachineSecret,
  MACHINE_SECRET_ENV,
  machineSecretFailure,
} from '../config-remote-machine-secret.js';

const API_URL = 'https://account.example.com';
const CONFIG_NAME = 'headless-ci';
const STORE_ID = '11111111-1111-4111-8111-111111111111';
const CONFIG_ID = '22222222-2222-4222-8222-222222222222';
const TEAM_ID = '33333333-3333-4333-8333-333333333333';
const SECRET_ID = '44444444-4444-4444-8444-444444444444';
const SDK_EPOCH = 7;

/** A real machine secret wrapping a real CEK, and a real encrypted config the probe pull opens. */
async function provision(secret: string, teamId: string | null = TEAM_ID) {
  const kdfParams = newMachineSecretParams();
  const serverSecret = generateServerSecret();
  const cek = await generateCek();
  const wrappedCek = await wrapCekForSlot(
    cek,
    await deriveMachineSecretSlotSecret(secret, kdfParams),
    serverSecret
  );
  const rawSdk = randomBytes(32);
  const payload = await buildConfigPushPayload(
    {
      id: CONFIG_ID,
      version: 1,
      resources: { machines: { m1: { ip: '10.0.0.9', port: 22 } } },
    } as unknown as RdcConfig,
    {
      storeId: STORE_ID,
      version: 1,
      sdkEpoch: SDK_EPOCH,
      sdkDerived: await importAesKey(rawSdk),
      cek,
      cekGeneration: 1,
      teamId: teamId ?? undefined,
    }
  );
  return {
    enroll: {
      machineSecretId: SECRET_ID,
      kdfParams,
      wrappedCek,
      cekGeneration: 1,
      token: 'rct_initial',
      storeId: STORE_ID,
      configId: CONFIG_ID,
      teamId,
    },
    session: {
      server_secret: toBase64(serverSecret),
      sdk_derived: toBase64(rawSdk),
      sdkEpoch: SDK_EPOCH,
    },
    config: {
      server_secret: toBase64(serverSecret),
      configData: payload.encryptedBlob,
      envelope: {
        envelopeVersion: payload.envelope.envelopeVersion,
        configId: CONFIG_ID,
        version: 1,
        teamId,
        lastModified: '2026-01-01T00:00:00Z',
        sdkEpoch: SDK_EPOCH,
        commitments: payload.envelope.commitments,
        wrappedConfigKey: payload.envelope.wrappedConfigKey,
        configKeyVersion: payload.envelope.configKeyVersion,
        cekGeneration: payload.envelope.cekGeneration,
      },
      hmac: payload.hmac,
      sdk_derived: toBase64(rawSdk),
    },
  };
}

function wireConfigApi(session: unknown, config: unknown) {
  mockConfigServerFetch.mockImplementation((path: string) => {
    if (path.includes('/configs/session')) return Promise.resolve({ data: session });
    return Promise.resolve({ data: config });
  });
}

describe('config remote enable --machine-secret', () => {
  const realIsTTY = Object.getOwnPropertyDescriptor(process.stdin, 'isTTY');
  const setTTY = (value: boolean | undefined) =>
    Object.defineProperty(process.stdin, 'isTTY', { value, configurable: true, writable: true });
  afterEach(() => {
    // Restore the stream's own descriptor, or remove ours so the prototype value shows again.
    if (realIsTTY) Object.defineProperty(process.stdin, 'isTTY', realIsTTY);
    else Reflect.deleteProperty(process.stdin, 'isTTY');
  });

  beforeEach(() => {
    vi.clearAllMocks();
    // Pinned so the suite takes the stdin branch whether or not it runs from a terminal.
    setTTY(false);
    secureMem.clear();
    tokenMem.clear();
    delete process.env[MACHINE_SECRET_ENV];
    delete process.env.REDIACC_TOKEN;
    mockReadStdinValue.mockResolvedValue('');
    const localConfig = {
      schemaVersion: 3,
      id: 'local-id',
      version: 1,
      account: { team: 'team', region: 'eu', accountServer: API_URL },
      defaults: { language: 'en' },
    };
    mockConfigFileStorage.load.mockResolvedValue(localConfig);
    mockConfigFileStorage.loadDecrypted.mockResolvedValue(localConfig);
    mockConfigFileStorage.save.mockResolvedValue(undefined);
    mockConfigFileStorage.getConfigPath.mockReturnValue(`/tmp/${CONFIG_NAME}.json`);
  });

  it('enrolls end to end with the secret from REDIACC_MACHINE_SECRET', async () => {
    const secret = generateMachineSecret();
    const f = await provision(secret);
    mockAccountServerFetch.mockResolvedValue(f.enroll);
    wireConfigApi(f.session, f.config);
    process.env[MACHINE_SECRET_ENV] = secret;
    process.env.REDIACC_TOKEN = 'rdt_enroll';

    await expect(enableMachineSecret(API_URL, CONFIG_NAME, SECRET_ID)).resolves.toBeUndefined();

    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/configs/machine-enroll',
      expect.objectContaining({
        method: 'POST',
        serverUrl: API_URL,
        token: 'rdt_enroll',
        body: { machineSecretId: SECRET_ID },
      })
    );
    // The derived wrapping secret is stored under a fresh key id; the secret itself is not.
    expect(secureMem.size).toBe(1);
    const [storageKeyId, stored] = [...secureMem.entries()][0];
    expect(storageKeyId).toMatch(/^rdc:ms:/);
    expect(stored).toBe(toBase64(await deriveMachineSecretSlotSecret(secret, f.enroll.kdfParams)));
    expect(stored).not.toContain(secret);
    expect(tokenMem.get(CONFIG_NAME)?.wrappedCek).toBe(f.enroll.wrappedCek);
    const savedPointer = mockConfigFileStorage.save.mock.calls.at(-1)?.[0];
    expect(savedPointer.remote).toMatchObject({
      apiUrl: API_URL,
      storeId: STORE_ID,
      configId: CONFIG_ID,
      teamId: TEAM_ID,
      storageKeyId,
    });
  });

  it('reads the secret from stdin when the environment holds none', async () => {
    const secret = generateMachineSecret();
    const f = await provision(secret, null);
    mockAccountServerFetch.mockResolvedValue(f.enroll);
    wireConfigApi(f.session, f.config);
    mockReadStdinValue.mockResolvedValue(`${secret.toLowerCase()}`);

    await expect(enableMachineSecret(API_URL, CONFIG_NAME, SECRET_ID)).resolves.toBeUndefined();
    expect(mockReadStdinValue).toHaveBeenCalledTimes(1);
    const savedPointer = mockConfigFileStorage.save.mock.calls.at(-1)?.[0];
    expect(savedPointer.remote.teamId).toBeUndefined();
  });

  it('asks on the terminal when stdin is a TTY (control for the pinned non-TTY branch)', async () => {
    const secret = generateMachineSecret();
    const f = await provision(secret, null);
    mockAccountServerFetch.mockResolvedValue(f.enroll);
    wireConfigApi(f.session, f.config);
    setTTY(true);
    mockAskPassword.mockResolvedValue(secret);

    await expect(enableMachineSecret(API_URL, CONFIG_NAME, SECRET_ID)).resolves.toBeUndefined();
    expect(mockAskPassword).toHaveBeenCalledTimes(1);
    expect(mockReadStdinValue).not.toHaveBeenCalled();
  });

  it('refuses an empty secret before any server call', async () => {
    // Stdin is pinned non-TTY, so the real prompt is never reached from a terminal run.
    expect(process.stdin.isTTY).toBe(false);
    await expect(enableMachineSecret(API_URL, CONFIG_NAME, SECRET_ID)).rejects.toThrow(
      /No machine secret was given: set REDIACC_MACHINE_SECRET/
    );
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('refuses a malformed secret before any server call', async () => {
    process.env[MACHINE_SECRET_ENV] = 'RM1-not-a-secret';
    await expect(enableMachineSecret(API_URL, CONFIG_NAME, SECRET_ID)).rejects.toThrow(
      /The machine secret is not valid/
    );
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('a wrong secret fails with a clean message and leaves nothing behind', async () => {
    const f = await provision(generateMachineSecret());
    mockAccountServerFetch.mockResolvedValue(f.enroll);
    wireConfigApi(f.session, f.config);
    process.env[MACHINE_SECRET_ENV] = generateMachineSecret();

    await expect(enableMachineSecret(API_URL, CONFIG_NAME, SECRET_ID)).rejects.toThrow(
      /Could not unlock the config with that machine secret/
    );
    expect(secureMem.size).toBe(0);
    expect(tokenMem.size).toBe(0);
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
  });

  const forbiddenCases: { name: string; error: object; expected: RegExp }[] = [
    {
      name: 'a revoked secret',
      error: { message: 'This machine secret was revoked; mint a new one in the portal.' },
      expected: /was revoked, or the store key was rotated/,
    },
    {
      name: 'a team the token does not cover',
      error: { message: 'no team', code: 'team_forbidden' },
      expected: /team is out of reach for this API token: no team/,
    },
    {
      name: 'a token missing the config:enroll scope',
      error: { message: 'Missing required scope: config:enroll' },
      expected: /does not carry the config:enroll scope/,
    },
    {
      name: 'a token with no user',
      error: { message: 'This token has no associated user and cannot enroll a machine.' },
      expected: /not tied to a user in an organization/,
    },
    {
      name: 'an unrecognised refusal',
      error: { message: 'Some future policy said no' },
      expected: /refused the machine enrollment: Some future policy said no/,
    },
  ];
  for (const { name, error, expected } of forbiddenCases) {
    it(`maps the 403 for ${name} to its own message and writes nothing`, async () => {
      process.env[MACHINE_SECRET_ENV] = generateMachineSecret();
      mockAccountServerFetch.mockRejectedValue(
        Object.assign(new Error((error as { message: string }).message), error, { status: 403 })
      );
      await expect(enableMachineSecret(API_URL, CONFIG_NAME, SECRET_ID)).rejects.toThrow(expected);
      expect(secureMem.size).toBe(0);
      expect(tokenMem.size).toBe(0);
    });
  }

  it('maps a 404 to the "not available to this token" message naming the id', async () => {
    process.env[MACHINE_SECRET_ENV] = generateMachineSecret();
    mockAccountServerFetch.mockRejectedValue(
      Object.assign(new Error(`Machine secret ${SECRET_ID} not found.`), { status: 404 })
    );
    await expect(enableMachineSecret(API_URL, CONFIG_NAME, SECRET_ID)).rejects.toThrow(
      new RegExp(`Machine secret ${SECRET_ID} is not available to this API token`)
    );
  });
});

describe('the enable command surface', () => {
  function enableCommand(): Command {
    const root = new Command('config');
    registerRemoteCommands(root);
    const remote = root.commands.find((c) => c.name() === 'remote');
    const enable = remote?.commands.find((c) => c.name() === 'enable');
    if (!enable) throw new Error('config remote enable is not registered');
    return enable;
  }

  it('takes the machine secret id as its only machine-secret option and no password option', () => {
    const flags = enableCommand().options.map((o) => o.flags);
    expect(flags).toContain('--machine-secret <id>');
    expect(flags.filter((f) => /password/i.test(f))).toEqual([]);
  });

  it('refuses --config-id beside --machine-secret before touching the config or the server', async () => {
    const exit = vi.spyOn(process, 'exit').mockImplementation((() => {
      throw new Error('process.exit');
    }) as never);
    const stderr = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
    const errorLog = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    try {
      await expect(
        enableCommand().parseAsync(['--machine-secret', SECRET_ID, '--config-id', CONFIG_ID], {
          from: 'user',
        })
      ).rejects.toThrow('process.exit');
      const printed = [...stderr.mock.calls, ...errorLog.mock.calls].flat().join(' ');
      expect(printed).toMatch(/--config-id cannot be combined with --machine-secret/);
      expect(mockConfigFileStorage.load).not.toHaveBeenCalled();
      expect(mockAccountServerFetch).not.toHaveBeenCalled();
    } finally {
      exit.mockRestore();
      stderr.mockRestore();
      errorLog.mockRestore();
    }
  });

  it('registers no master-password subcommand under config remote', () => {
    const root = new Command('config');
    registerRemoteCommands(root);
    const remote = root.commands.find((c) => c.name() === 'remote');
    expect(remote?.commands.map((c) => c.name())).not.toContain('master-password');
  });

  it('the enroll module reads the secret from the environment or stdin only, never argv', () => {
    const source = readFileSync(
      fileURLToPath(new URL('../config-remote-machine-secret.ts', import.meta.url)),
      'utf8'
    );
    expect(source).not.toMatch(/process\.argv/);
    expect(source).toContain('process.env[MACHINE_SECRET_ENV]');
    expect(source).toContain('readStdinValue');
  });
});

// Review 1121-1 a5d16e9e.1: only an unwrap failure (no cause) means the secret was wrong.
describe('machineSecretFailure', () => {
  it('names a wrong secret for the unwrap failure, which carries no cause', async () => {
    const failure = await machineSecretFailure(new RemoteStaleSlotError(undefined, CONFIG_NAME));
    expect((failure as Error).message).toContain(MACHINE_SECRET_ENV);
    expect(failure).not.toBeInstanceOf(RemoteStaleSlotError);
  });

  it('keeps the rotated-key error, whose cause is the diagnosed failure, as it was', async () => {
    const rotated = new RemoteStaleSlotError({ cause: new Error('OperationError') }, CONFIG_NAME);
    expect(await machineSecretFailure(rotated)).toBe(rotated);
  });

  it('passes any other error through', async () => {
    const other = new Error('boom');
    expect(await machineSecretFailure(other)).toBe(other);
  });
});
