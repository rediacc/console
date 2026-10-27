/**
 * R1 (PLAN-backup-program): rdc 1.3.12 refused a v3-envelope config (eu-remote's shape) with the
 * slot-key text, because it predates envelope v3 and reads every pull as v2, so the CEK layer's
 * check failed. That is format skew, not a slot-key mismatch. These pin the current reader:
 * it reads a v3 envelope, and an envelope newer than it reads names the version gap instead of
 * the slot key. The fixture is synthetic (random keys, no real config).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockConfigServerFetch } = vi.hoisted(() => ({ mockConfigServerFetch: vi.fn() }));

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
import type { RdcConfig, RemoteConfig } from '../../types/index.js';
import { RemoteConfigAdapter, RemoteConfigUndecryptableError } from '../remote-config-adapter.js';
import type { RemoteTokenStorage } from '../remote-token-storage.js';

const STORE_ID = '11111111-1111-4111-8111-111111111111';
const CONFIG_ID = '22222222-2222-4222-8222-222222222222';
const TEAM_ID = '33333333-3333-4333-8333-333333333333';
const SDK_EPOCH = 11;

const REMOTE: RemoteConfig = {
  apiUrl: 'https://account.example.com',
  storeId: STORE_ID,
  configId: CONFIG_ID,
  teamId: TEAM_ID,
  storageKeyId: 'rdc:pw:44444444-4444-4444-8444-444444444444',
};

/** A v3-envelope config of eu-remote's shape (schemaVersion 3, resources), sealed by the current code. */
async function enrolled() {
  const slotSecret = await derivePasswordSlotSecret('fixture password', newPasswordSlotParams());
  const serverSecret = generateServerSecret();
  const cek = await generateCek();
  const wrappedCek = await wrapCekForSlot(cek, slotSecret, serverSecret);
  const rawSdk = randomBytes(32);
  const payload = await buildConfigPushPayload(
    {
      schemaVersion: 3,
      id: CONFIG_ID,
      version: 7,
      resources: { machines: { m1: { ip: '10.0.0.9', port: 22 } } },
    } as unknown as RdcConfig,
    {
      storeId: STORE_ID,
      version: 7,
      sdkEpoch: SDK_EPOCH,
      sdkDerived: await importAesKey(rawSdk),
      cek,
      teamId: TEAM_ID,
    }
  );
  const pull = (envelopeVersion: number) => ({
    server_secret: toBase64(serverSecret),
    configData: payload.encryptedBlob,
    envelope: {
      envelopeVersion,
      configId: CONFIG_ID,
      version: 7,
      teamId: TEAM_ID,
      lastModified: '2026-01-01T00:00:00Z',
      sdkEpoch: SDK_EPOCH,
      commitments: payload.envelope.commitments,
    },
    hmac: payload.hmac,
    sdk_derived: toBase64(rawSdk),
  });
  const session = {
    server_secret: toBase64(serverSecret),
    sdk_derived: toBase64(rawSdk),
    sdkEpoch: SDK_EPOCH,
  };
  const adapter = (): RemoteConfigAdapter => {
    const entry = { token: 'rct_1', wrappedCek };
    const tokens = {
      get: vi.fn().mockResolvedValue(entry),
      set: vi.fn().mockResolvedValue(undefined),
      updateToken: vi.fn().mockResolvedValue(undefined),
      delete: vi.fn().mockResolvedValue(undefined),
      withLease: <T>(_n: string, fn: (lease: unknown) => Promise<T>) =>
        fn({
          data: entry,
          token: entry.token,
          sync: undefined,
          update: () => Promise.resolve(),
          recordSync: () => Promise.resolve(),
        }),
    };
    const secure = {
      get: vi.fn().mockResolvedValue(toBase64(slotSecret)),
      set: vi.fn().mockResolvedValue(undefined),
      delete: vi.fn().mockResolvedValue(undefined),
      type: 'mem',
    };
    return new RemoteConfigAdapter(
      REMOTE,
      'envelope-skew',
      tokens as unknown as RemoteTokenStorage,
      secure
    );
  };
  return { pull, session, adapter };
}

function wire(session: unknown, pulled: unknown) {
  mockConfigServerFetch.mockImplementation((path: string) =>
    Promise.resolve({ data: path.includes('/configs/session') ? session : pulled })
  );
}

describe('RemoteConfigAdapter: envelope skew between rdc releases', () => {
  beforeEach(() => {
    mockConfigServerFetch.mockReset();
  });

  it('reads a config enrolled by the current code (v3 envelope)', async () => {
    const f = await enrolled();
    wire(f.session, f.pull(3));
    const result = await f.adapter().pull();
    expect(result.version).toBe(7);
    expect(result.config.resources?.machines?.m1).toMatchObject({ ip: '10.0.0.9' });
  });

  it('an old reader (envelope labelled v2) fails closed, never returning the config', async () => {
    const f = await enrolled();
    wire(f.session, f.pull(2));
    await expect(f.adapter().pull()).rejects.toBeInstanceOf(RemoteConfigUndecryptableError);
  });

  it('an envelope newer than this reader names the version gap, not the slot key', async () => {
    const f = await enrolled();
    wire(f.session, f.pull(4));
    const err = await f
      .adapter()
      .pull()
      .then(
        () => null,
        (e: unknown) => e
      );
    expect(err).toBeInstanceOf(RemoteConfigUndecryptableError);
    const message = (err as Error).message;
    expect(message).toContain(CONFIG_ID);
    expect(message).toMatch(/newer version of the CLI/);
    expect(message).toContain('envelope v4');
    expect(message).toMatch(/Upgrade rdc/);
    expect(message).not.toMatch(/key slot|enrolled|different key/i);
  });
});
