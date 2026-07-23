/**
 * Headless password enrollment (`rdc config remote enable --password`).
 *
 * The crypto is REAL here on purpose: the plan bans a mocked-crypto-only proof
 * for this path. We build a genuine password slot (derive → wrap a real CEK under
 * the derived slot secret + serverSecret), stand up a genuine encrypted config
 * blob, and let the enroll flow's probe pull unwrap it end to end. Only the I/O
 * seams (account API, config API, OS secure storage, config + token files) are
 * mocked; every AES/HKDF/PBKDF2 operation runs for real.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

// ─── Hoisted I/O mocks (crypto stays real) ───────────────────────────────

const {
  mockAccountServerFetch,
  mockConfigServerFetch,
  secureMem,
  tokenMem,
  mockConfigFileStorage,
} = vi.hoisted(() => ({
  mockAccountServerFetch: vi.fn(),
  mockConfigServerFetch: vi.fn(),
  secureMem: new Map<string, string>(),
  tokenMem: new Map<string, { token: string; wrappedCek: string }>(),
  mockConfigFileStorage: {
    load: vi.fn(),
    loadDecrypted: vi.fn(),
    save: vi.fn(),
    getConfigPath: vi.fn(),
  },
}));

vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: mockAccountServerFetch,
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
    set: (name: string, data: { token: string; wrappedCek: string }) => {
      tokenMem.set(name, data);
      return Promise.resolve();
    },
    updateToken: (name: string, token: string) => {
      const cur = tokenMem.get(name);
      if (cur) tokenMem.set(name, { ...cur, token });
      return Promise.resolve();
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

// Real crypto — do NOT mock @rediacc/shared/*.
import {
  derivePasswordSlotSecret,
  generateCek,
  generateServerSecret,
  importAesKey,
  newPasswordSlotParams,
  randomBytes,
  toBase64,
  wrapCekForSlot,
} from '@rediacc/shared/config-crypto';
import { buildConfigPushPayload } from '@rediacc/shared/config-schema';
import type { RdcConfig } from '../../types/index.js';
import { enablePassword } from '../config-remote-password.js';

// ─── Fixture constants ───────────────────────────────────────────────────

const API_URL = 'https://account.example.com';
const CONFIG_NAME = 'headless-ci';
const STORE_ID = '11111111-1111-4111-8111-111111111111';
const CONFIG_ID = '22222222-2222-4222-8222-222222222222';
const TEAM_ID = '33333333-3333-4333-8333-333333333333';
const PASSWORD = 'correct horse battery staple';
const SDK_EPOCH = 7;

/**
 * Provision a real password slot + a real encrypted config the probe pull can
 * open. Returns the enroll response the server would send and the wired config
 * API responses (session + config) sealed to the SAME CEK.
 */
async function provision(password: string, teamId: string | null = TEAM_ID) {
  const kdfParams = newPasswordSlotParams();
  const slotSecret = await derivePasswordSlotSecret(password, kdfParams);
  const serverSecret = generateServerSecret();
  const cek = await generateCek();
  const wrappedCek = await wrapCekForSlot(cek, slotSecret, serverSecret);

  const rawSdk = randomBytes(32);
  const sdkDerived = await importAesKey(rawSdk);

  const configInput = {
    id: CONFIG_ID,
    version: 1,
    resources: { machines: { m1: { ip: '10.0.0.9', port: 22 } } },
  } as unknown as RdcConfig;

  const payload = await buildConfigPushPayload(configInput, {
    version: 1,
    sdkEpoch: SDK_EPOCH,
    sdkDerived,
    cek,
    teamId: teamId ?? undefined,
  });

  return {
    enroll: {
      method: 'password' as const,
      kdfParams,
      wrappedCek,
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
      configData: payload.encryptedBlob,
      envelope: {
        configId: CONFIG_ID,
        version: 1,
        teamId,
        lastModified: '2026-01-01T00:00:00Z',
        commitments: payload.envelope.commitments,
      },
      hmac: payload.hmac,
    },
  };
}

/** Route the config API mock to session vs config-pull by path. */
function wireConfigApi(session: unknown, config: unknown) {
  mockConfigServerFetch.mockImplementation((path: string) => {
    if (path.includes('/configs/session')) return Promise.resolve({ data: session });
    return Promise.resolve({ data: config });
  });
}

describe('config remote enable --password', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    secureMem.clear();
    tokenMem.clear();
    delete process.env.REDIACC_CONFIG_PASSWORD;
    delete process.env.REDIACC_TOKEN;
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

  it('unlocks a pre-provisioned slot end to end (derive → wrap → enroll → probe unwrap)', async () => {
    const f = await provision(PASSWORD);
    mockAccountServerFetch.mockResolvedValue(f.enroll);
    wireConfigApi(f.session, f.config);
    process.env.REDIACC_CONFIG_PASSWORD = PASSWORD;

    await expect(enablePassword(API_URL, CONFIG_NAME)).resolves.toBeUndefined();

    // Empty body; userId is resolved server-side from the token.
    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/configs/password-enroll',
      expect.objectContaining({ method: 'POST', serverUrl: API_URL, body: {} })
    );

    // Slot secret persisted under a fresh key id; token + wrappedCek persisted.
    expect(secureMem.size).toBe(1);
    const [storageKeyId, storedSecret] = [...secureMem.entries()][0];
    expect(storageKeyId).toMatch(/^rdc:pw:/);
    expect(storedSecret).toBe(
      toBase64(await derivePasswordSlotSecret(PASSWORD, f.enroll.kdfParams))
    );
    expect(tokenMem.get(CONFIG_NAME)?.wrappedCek).toBe(f.enroll.wrappedCek);

    // Pointer written only after the probe pull opened the config.
    const savedPointer = mockConfigFileStorage.save.mock.calls.at(-1)?.[0];
    expect(savedPointer.remote).toMatchObject({
      apiUrl: API_URL,
      storeId: STORE_ID,
      configId: CONFIG_ID,
      teamId: TEAM_ID,
      storageKeyId,
    });
  });

  it('collapses a null teamId (default config) to an undefined pointer field', async () => {
    const f = await provision(PASSWORD, null);
    mockAccountServerFetch.mockResolvedValue(f.enroll);
    wireConfigApi(f.session, f.config);
    process.env.REDIACC_CONFIG_PASSWORD = PASSWORD;

    await enablePassword(API_URL, CONFIG_NAME);

    const savedPointer = mockConfigFileStorage.save.mock.calls.at(-1)?.[0];
    expect(savedPointer.remote.teamId).toBeUndefined();
    expect('teamId' in savedPointer.remote).toBe(true);
  });

  it('passes REDIACC_TOKEN through as the enroll bearer token', async () => {
    const f = await provision(PASSWORD);
    mockAccountServerFetch.mockResolvedValue(f.enroll);
    wireConfigApi(f.session, f.config);
    process.env.REDIACC_CONFIG_PASSWORD = PASSWORD;
    process.env.REDIACC_TOKEN = 'rdc_api_tok_abc';

    await enablePassword(API_URL, CONFIG_NAME);

    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/configs/password-enroll',
      expect.objectContaining({ token: 'rdc_api_tok_abc' })
    );
  });

  it('fails with a clean message on a wrong password and cleans up artifacts', async () => {
    // Slot provisioned under the RIGHT password; box supplies the WRONG one.
    const f = await provision(PASSWORD);
    mockAccountServerFetch.mockResolvedValue(f.enroll);
    wireConfigApi(f.session, f.config);
    process.env.REDIACC_CONFIG_PASSWORD = 'wrong password entirely';

    await expect(enablePassword(API_URL, CONFIG_NAME)).rejects.toThrow(
      /Could not unlock the config with that password/
    );

    // No stored artifacts survive a failed probe.
    expect(secureMem.size).toBe(0);
    expect(tokenMem.size).toBe(0);
    // The stripped pointer was never written.
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
  });

  it('maps a 403 to the requirePasskey message and writes nothing', async () => {
    mockAccountServerFetch.mockRejectedValue(
      Object.assign(new Error('Forbidden'), { status: 403 })
    );
    process.env.REDIACC_CONFIG_PASSWORD = PASSWORD;

    await expect(enablePassword(API_URL, CONFIG_NAME)).rejects.toThrow(
      /requires a passkey to unlock config storage/
    );
    expect(secureMem.size).toBe(0);
    expect(tokenMem.size).toBe(0);
  });

  it('maps a 404 to the "no password slot provisioned" message', async () => {
    mockAccountServerFetch.mockRejectedValue(
      Object.assign(new Error('Not found'), { status: 404 })
    );
    process.env.REDIACC_CONFIG_PASSWORD = PASSWORD;

    await expect(enablePassword(API_URL, CONFIG_NAME)).rejects.toThrow(
      /No password slot is provisioned/
    );
  });

  it('requires REDIACC_CONFIG_PASSWORD when stdin is not a TTY', async () => {
    const f = await provision(PASSWORD);
    mockAccountServerFetch.mockResolvedValue(f.enroll);
    wireConfigApi(f.session, f.config);
    // No REDIACC_CONFIG_PASSWORD set; vitest stdin is not a TTY.

    await expect(enablePassword(API_URL, CONFIG_NAME)).rejects.toThrow(
      /config master password is required/
    );
  });
});
