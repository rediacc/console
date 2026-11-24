/**
 * The CLI on envelope v4 (PLAN-rmcp-policy-record.md SK3): real crypto through `RemoteConfigAdapter`,
 * with only the HTTP boundary (`config-server-client`) replaced by a one-config store.
 *
 * - A pull of a v4 config opens through its content key and records the wrap in the sync record.
 * - A push is sealed as v4 under that same content key: the key version stays, the commitment keys
 *   stay, and the recorded wrap moves to the pushed one.
 * - A pulled envelope below the version this device recorded is refused as a downgrade.
 * - A push with no known CEK generation fails before the PUT.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockConfigServerFetch } = vi.hoisted(() => ({ mockConfigServerFetch: vi.fn() }));

vi.mock('../config-server-client.js', () => ({
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
  computeCommitments,
  configEncrypt,
  deriveFieldCommitmentKey,
  derivePointerBlindingKey,
  deriveRecoverySlotSecret,
  type EncryptedConfigPayload,
  envelopeAad,
  exportAesKey,
  generateCek,
  generateFckSalt,
  generateRecoveryCode,
  generateServerSecret,
  importAesKey,
  newRecoverySlotParams,
  randomBytes,
  toBase64,
  unwrapEnvelopeConfigKey,
  wrapCekForSlot,
} from '@rediacc/shared/config-crypto';
import {
  buildCommitEntries,
  buildConfigPushPayload,
  toFullConfig,
} from '@rediacc/shared/config-schema';
import {
  RemoteConfigAdapter,
  RemoteRollbackError,
} from '../../../adapters/remote-config-adapter.js';
import type { RemoteTokenStorage, SyncRecord } from '../../../adapters/remote-token-storage.js';
import type { RdcConfig, RemoteConfig } from '../../../types/index.js';
import { omitKey } from '../../../utils/omit-key.js';

const STORE_ID = '11111111-1111-4111-8111-111111111111';
const CONFIG_ID = '22222222-2222-4222-8222-222222222222';
const SDK_EPOCH = 11;
const GENERATION = 1;
const BINDING = { storeId: STORE_ID, configId: CONFIG_ID, teamId: null };

const REMOTE: RemoteConfig = {
  apiUrl: 'https://account.example.com',
  storeId: STORE_ID,
  configId: CONFIG_ID,
  storageKeyId: 'rdc:pw:44444444-4444-4444-8444-444444444444',
};

function doc(version: number, machines: Record<string, { ip: string; port: number }>): RdcConfig {
  return {
    schemaVersion: 3,
    id: CONFIG_ID,
    version,
    resources: { machines, repositories: {} },
  } as unknown as RdcConfig;
}

const M1 = { m1: { ip: '10.0.0.9', port: 22 } };
const M1_M2 = { ...M1, m2: { ip: '10.0.0.10', port: 22 } };

/** The account server, reduced to one config: what the last push (or the seed) stored, served back on every pull. */
async function world(options: { sessionGeneration?: number | null } = {}) {
  const slotSecret = await deriveRecoverySlotSecret(
    generateRecoveryCode(),
    newRecoverySlotParams()
  );
  const serverSecret = generateServerSecret();
  const cek = await generateCek();
  const wrappedCek = await wrapCekForSlot(cek, slotSecret, serverSecret);
  const rawSdk = randomBytes(32);
  const sdkDerived = await importAesKey(rawSdk);
  const seed = await buildConfigPushPayload(doc(1, M1), {
    storeId: STORE_ID,
    version: 1,
    sdkEpoch: SDK_EPOCH,
    sdkDerived,
    cek,
    cekGeneration: GENERATION,
  });
  const state = {
    stored: { version: 1, payload: seed as EncryptedConfigPayload },
    puts: [] as { envelope: EncryptedConfigPayload['envelope']; cekGeneration?: number }[],
  };
  const sessionGeneration =
    options.sessionGeneration === undefined ? GENERATION : options.sessionGeneration;

  mockConfigServerFetch.mockImplementation(
    (path: string, init: { method?: string; body?: Record<string, unknown> }) => {
      if (path.endsWith('/configs/session')) {
        return Promise.resolve({
          data: {
            server_secret: toBase64(serverSecret),
            sdk_derived: toBase64(rawSdk),
            sdkEpoch: SDK_EPOCH,
            ...(sessionGeneration === null ? {} : { cekGeneration: sessionGeneration }),
          },
        });
      }
      if (init.method === 'PUT') {
        const body = init.body as {
          version: number;
          encryptedBlob: string;
          envelope: EncryptedConfigPayload['envelope'];
          cekGeneration?: number;
        };
        state.puts.push({ envelope: body.envelope, cekGeneration: body.cekGeneration });
        const kept = omitKey(omitKey(body.envelope.commitments, 'removed'), 'migrated');
        state.stored = {
          version: body.version,
          payload: {
            envelope: { ...body.envelope, commitments: kept },
            encryptedBlob: body.encryptedBlob,
          },
        };
        return Promise.resolve({ data: { version: body.version, cekGeneration: GENERATION } });
      }
      const { envelope, encryptedBlob, hmac } = state.stored.payload;
      return Promise.resolve({
        data: {
          server_secret: toBase64(serverSecret),
          sdk_derived: toBase64(rawSdk),
          configData: encryptedBlob,
          envelope: {
            ...envelope,
            configId: CONFIG_ID,
            teamId: null,
            lastModified: '2026-11-23T00:00:00Z',
          },
          hmac: hmac ?? null,
          cekGeneration: GENERATION,
        },
      });
    }
  );

  let current: { token: string; wrappedCek: string; sync?: SyncRecord } = {
    token: 'rct_1',
    wrappedCek,
  };
  const tokens = {
    withLease: <T>(_name: string, fn: (lease: unknown) => Promise<T>) =>
      fn({
        data: current,
        get token() {
          return current.token;
        },
        get sync() {
          return current.sync;
        },
        update: (token: string) => {
          current = { ...current, token };
          return Promise.resolve();
        },
        recordSync: (sync: SyncRecord) => {
          current = { ...current, sync };
          return Promise.resolve();
        },
      }),
  };
  const secure = {
    get: vi.fn().mockResolvedValue(toBase64(slotSecret)),
    set: vi.fn(),
    delete: vi.fn(),
    type: 'mem',
  };
  const adapter = new RemoteConfigAdapter(
    REMOTE,
    'envelope-v4',
    tokens as unknown as RemoteTokenStorage,
    secure
  );

  /** Replace the stored copy with an envelope v3 at `version`, as a pre-v4 client sealed it. */
  async function storeV3(version: number) {
    const config = doc(version, M1);
    const full = toFullConfig(config, { version, sdkEpoch: SDK_EPOCH });
    const fckSalt = generateFckSalt();
    const commitments = await computeCommitments(
      await deriveFieldCommitmentKey(cek, fckSalt),
      fckSalt,
      buildCommitEntries(config),
      await derivePointerBlindingKey(cek, CONFIG_ID)
    );
    const envelope = {
      envelopeVersion: 3 as const,
      id: CONFIG_ID,
      version,
      sdkEpoch: SDK_EPOCH,
      commitments,
    };
    const blob = ['envelopeVersion', 'id', 'version', 'sdkEpoch', 'commitments'].reduce<
      Record<string, unknown>
    >((rest, key) => omitKey(rest, key), full);
    const encryptedBlob = await configEncrypt(
      JSON.stringify(blob),
      sdkDerived,
      cek,
      await envelopeAad(BINDING, envelope)
    );
    state.stored = { version, payload: { envelope, encryptedBlob } };
  }

  /** The raw bytes of the content key an envelope wraps. */
  async function contentKeyOf(envelope: EncryptedConfigPayload['envelope']) {
    return toBase64(await exportAesKey(await unwrapEnvelopeConfigKey(envelope, cek, BINDING)));
  }

  return { adapter, state, storeV3, contentKeyOf, sync: () => current.sync };
}

describe('the CLI on envelope v4', () => {
  beforeEach(() => {
    mockConfigServerFetch.mockReset();
  });

  it('a pull of a v4 config opens and records the content-key wrap', async () => {
    const w = await world();
    const pulled = await w.adapter.pull();
    expect(pulled.version).toBe(1);
    expect(pulled.config.resources?.machines).toEqual(M1);
    const stored = w.state.stored.payload.envelope;
    expect(w.sync()).toMatchObject({
      envelopeVersion: 4,
      highWater: 1,
      cekGeneration: GENERATION,
      configKey: {
        wrappedConfigKey: stored.wrappedConfigKey,
        configKeyVersion: 1,
        cekGeneration: GENERATION,
      },
    });
  });

  it('pushes v4 under the pulled content key, records the new wrap, and a second push keeps the key', async () => {
    const w = await world();
    await w.adapter.pull();
    const seeded = w.state.stored.payload.envelope;
    const seededKey = await w.contentKeyOf(seeded);

    await w.adapter.push(doc(1, M1_M2), 1, { base: doc(1, M1) });
    const first = w.state.puts[0];
    expect(first?.envelope.envelopeVersion).toBe(4);
    expect(first?.envelope.configKeyVersion).toBe(1);
    expect(first?.envelope.cekGeneration).toBe(GENERATION);
    expect(first?.cekGeneration).toBe(GENERATION);
    expect(await w.contentKeyOf(first?.envelope ?? seeded)).toBe(seededKey);
    // Same content key, so every stored commitment key is committed again and no key map is sent.
    expect(first?.envelope.commitments.migrated).toBeUndefined();
    for (const key of Object.keys(seeded.commitments.fields)) {
      expect(first?.envelope.commitments.fields).toHaveProperty([key]);
    }
    expect(w.sync()).toMatchObject({
      envelopeVersion: 4,
      highWater: 2,
      configKey: { wrappedConfigKey: first?.envelope.wrappedConfigKey, configKeyVersion: 1 },
    });

    await w.adapter.push(doc(2, M1), 2, { base: doc(2, M1_M2) });
    const second = w.state.puts[1];
    expect(second?.envelope.configKeyVersion).toBe(1);
    expect(await w.contentKeyOf(second?.envelope ?? seeded)).toBe(seededKey);
    expect(Object.keys(second?.envelope.commitments.removed ?? {}).length).toBeGreaterThan(0);
  });

  it('refuses a pulled envelope below the version this device recorded', async () => {
    const w = await world();
    await w.adapter.pull();
    await w.storeV3(5);
    await expect(w.adapter.pull()).rejects.toBeInstanceOf(RemoteRollbackError);
    expect(w.sync()).toMatchObject({ envelopeVersion: 4, highWater: 1 });
  });

  it('control: the same v3 copy opens for a device that recorded no newer envelope', async () => {
    const w = await world();
    await w.storeV3(5);
    const pulled = await w.adapter.pull();
    expect(pulled.version).toBe(5);
    expect(w.sync()).toMatchObject({ envelopeVersion: 3, highWater: 5 });
    expect(w.sync()?.configKey).toBeUndefined();
  });

  it('a push with no known CEK generation fails before the PUT', async () => {
    const w = await world({ sessionGeneration: null });
    await expect(w.adapter.push(doc(1, M1_M2), 1)).rejects.toThrow(/CEK generation/);
    expect(w.state.puts).toHaveLength(0);
    expect(mockConfigServerFetch.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false);
  });

  it('control: the same push with the generation named by /session goes through as v4', async () => {
    const w = await world();
    await w.adapter.push(doc(1, M1_M2), 1);
    expect(w.state.puts).toHaveLength(1);
    expect(w.state.puts[0]?.envelope.envelopeVersion).toBe(4);
  });
});
