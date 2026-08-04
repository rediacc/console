/**
 * Real-crypto companion to `remote-config-adapter.test.ts`.
 *
 * The sibling test mocks `@rediacc/shared/config-crypto` wholesale, which proves
 * the adapter's control flow but says nothing about whether the CLI actually
 * recovers the right CEK. This test keeps the crypto REAL: it stands up a genuine
 * password key-slot with the shared module (generateCek → newPasswordSlotParams →
 * derivePasswordSlotSecret → wrapCekForSlot), seals a real config blob under that
 * exact CEK, then drives the CLI's OWN unwrap path — `RemoteConfigAdapter.pull()`,
 * whose private `deriveCek` runs `deriveWrappingKey` + `cekUnwrap` — and asserts:
 *
 *   1. positive round-trip: the CEK the CLI unwraps is byte-identical to the CEK
 *      the slot was wrapped with (captured via a real-implementation spy on
 *      `cekUnwrap` + `exportAesKey` raw compare), and the config plaintext the CLI
 *      returns matches what was encrypted;
 *   2. wrong password → the slot secret no longer unwraps → RemoteStaleSlotError;
 *   3. a rotated/stale wrappedCek (generation mismatch) → RemoteStaleSlotError,
 *      i.e. the CLI surfaces its actionable re-enroll error.
 *
 * Only the HTTP boundary (`config-server-client`) is mocked; every AES/HKDF/PBKDF2
 * operation runs for real, and token + secure storage are plain in-memory stubs
 * passed straight to the adapter constructor.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

// ─── Mock ONLY the HTTP boundary; crypto stays real ──────────────────────

const { mockConfigServerFetch } = vi.hoisted(() => ({
  mockConfigServerFetch: vi.fn(),
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

// Real crypto — do NOT mock @rediacc/shared/*.
import * as configCrypto from '@rediacc/shared/config-crypto';
import {
  derivePasswordSlotSecret,
  exportAesKey,
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
import {
  RemoteConfigAdapter,
  RemoteConfigUndecryptableError,
  RemoteStaleSlotError,
} from '../remote-config-adapter.js';
import type { RemoteTokenStorage } from '../remote-token-storage.js';

// ─── Fixture constants ───────────────────────────────────────────────────

const API_URL = 'https://account.example.com';
const CONFIG_NAME = 'real-crypto';
const STORE_ID = '11111111-1111-4111-8111-111111111111';
const CONFIG_ID = '22222222-2222-4222-8222-222222222222';
const TEAM_ID = '33333333-3333-4333-8333-333333333333';
const STORAGE_KEY_ID = 'rdc:pw:44444444-4444-4444-8444-444444444444';
const PASSWORD = 'correct horse battery staple';
const SDK_EPOCH = 11;

const REMOTE: RemoteConfig = {
  apiUrl: API_URL,
  storeId: STORE_ID,
  configId: CONFIG_ID,
  teamId: TEAM_ID,
  storageKeyId: STORAGE_KEY_ID,
};

// ─── In-memory storage stubs (no module mock — passed to the constructor) ─

function createTokenStorage(entry: { token: string; wrappedCek: string } | null) {
  return {
    get: vi.fn().mockResolvedValue(entry),
    set: vi.fn().mockResolvedValue(undefined),
    updateToken: vi.fn().mockResolvedValue(undefined),
    delete: vi.fn().mockResolvedValue(undefined),
  };
}

function createSecureStorage(secretB64: string | null) {
  return {
    get: vi.fn().mockResolvedValue(secretB64),
    set: vi.fn().mockResolvedValue(undefined),
    delete: vi.fn().mockResolvedValue(undefined),
    type: 'mem',
  };
}

/**
 * Provision a genuine password slot + a genuine encrypted config sealed under the
 * SAME CEK. Returns the raw CEK (for the byte compare), the slot secret bytes,
 * the opaque wrappedCek, and the session + config-pull responses the config API
 * would serve.
 */
async function provision(
  password: string,
  teamId: string | null = TEAM_ID,
  opts: { wrapServerSecret?: Uint8Array; wrapCek?: CryptoKey } = {}
) {
  const kdfParams = newPasswordSlotParams();
  const slotSecret = await derivePasswordSlotSecret(password, kdfParams);
  const serverSecret = generateServerSecret();
  const cek = await generateCek();

  // The wrappedCek may deliberately be wrapped under a DIFFERENT server secret or
  // CEK to model a rotation the device never re-wrapped for (stale slot).
  const wrappedCek = await wrapCekForSlot(
    opts.wrapCek ?? cek,
    slotSecret,
    opts.wrapServerSecret ?? serverSecret
  );

  const rawSdk = randomBytes(32);
  const sdkDerived = await importAesKey(rawSdk);

  const configInput = {
    schemaVersion: 3,
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
    cek,
    slotSecret,
    wrappedCek,
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

describe('RemoteConfigAdapter — real crypto round-trip', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockConfigServerFetch.mockReset();
  });

  it('unwraps the identical CEK bytes the slot was wrapped with (derive → wrap → CLI unwrap)', async () => {
    const f = await provision(PASSWORD);
    wireConfigApi(f.session, f.config);

    // Spy on the shared cekUnwrap but keep the REAL implementation, so we can
    // read back exactly which CEK the CLI's deriveCek produced.
    const unwrapSpy = vi.spyOn(configCrypto, 'cekUnwrap');

    const adapter = new RemoteConfigAdapter(
      REMOTE,
      CONFIG_NAME,
      createTokenStorage({
        token: 'rct_1',
        wrappedCek: f.wrappedCek,
      }) as unknown as RemoteTokenStorage,
      createSecureStorage(toBase64(f.slotSecret))
    );

    const result = await adapter.pull();

    // The CLI drove a real cekUnwrap and recovered the config plaintext.
    expect(unwrapSpy).toHaveBeenCalledTimes(1);
    expect(result.version).toBe(1);
    expect(result.sdkEpoch).toBe(SDK_EPOCH);
    expect(result.config.resources?.machines).toHaveProperty('m1');
    expect(result.config.resources?.machines?.m1).toMatchObject({ ip: '10.0.0.9', port: 22 });

    // Byte-for-byte: the CEK the CLI unwrapped equals the CEK we wrapped the slot
    // with. Compare raw AES key material via exportAesKey.
    const recoveredCek = await unwrapSpy.mock.results[0]?.value;
    const recoveredRaw = await exportAesKey(recoveredCek as CryptoKey);
    const expectedRaw = await exportAesKey(f.cek);
    expect(Buffer.from(recoveredRaw)).toEqual(Buffer.from(expectedRaw));
  });

  it('rejects with RemoteStaleSlotError when the password (slot secret) is wrong', async () => {
    // Slot + config sealed under PASSWORD; the device holds the WRONG slot secret.
    const f = await provision(PASSWORD);
    wireConfigApi(f.session, f.config);

    const wrongKdf = newPasswordSlotParams();
    const wrongSlotSecret = await derivePasswordSlotSecret('a different password', wrongKdf);

    const adapter = new RemoteConfigAdapter(
      REMOTE,
      CONFIG_NAME,
      createTokenStorage({
        token: 'rct_1',
        wrappedCek: f.wrappedCek,
      }) as unknown as RemoteTokenStorage,
      createSecureStorage(toBase64(wrongSlotSecret))
    );

    await expect(adapter.pull()).rejects.toBeInstanceOf(RemoteStaleSlotError);
  });

  it('rejects with RemoteStaleSlotError on a rotated/stale wrappedCek (generation mismatch)', async () => {
    // The slot secret is CORRECT, but the stored wrappedCek was wrapped under a
    // different server secret — i.e. the CEK was rotated and this device kept its
    // old wrapping. The AES-GCM auth tag fails and the CLI surfaces its re-enroll
    // error rather than a raw OperationError.
    const rotatedServerSecret = generateServerSecret();
    const f = await provision(PASSWORD, TEAM_ID, { wrapServerSecret: rotatedServerSecret });
    wireConfigApi(f.session, f.config);

    const adapter = new RemoteConfigAdapter(
      REMOTE,
      CONFIG_NAME,
      createTokenStorage({
        token: 'rct_1',
        wrappedCek: f.wrappedCek,
      }) as unknown as RemoteTokenStorage,
      createSecureStorage(toBase64(f.slotSecret))
    );

    const err = await adapter.pull().then(
      () => null,
      (e: unknown) => e
    );
    expect(err).toBeInstanceOf(RemoteStaleSlotError);
    // The surfaced message points the user at re-enrollment.
    expect((err as RemoteStaleSlotError).message).toMatch(/re-?enroll/i);
  });

  // ─── F5: the blob refuses AFTER a successful CEK unwrap ────────────────
  //
  // Enrolling a fresh device against a store that already holds a DIFFERENT
  // config for the org used to die with a raw WebCrypto
  // "OperationError: The operation failed for an operation-specific reason",
  // because the only crypto catch in pull() wraps cekUnwrap, and here the
  // unwrap SUCCEEDS. The failure is one layer later, in selectiveDecrypt.

  it('names the store/config mismatch when the blob was sealed under another CEK', async () => {
    // The slot wraps CEK-B; the stored blob was sealed under CEK-A. The device
    // unwraps CEK-B cleanly and then meets a config it cannot read: exactly the
    // "store already holds a different config for this org" case.
    const otherCek = await generateCek();
    const f = await provision(PASSWORD, TEAM_ID, { wrapCek: otherCek });
    wireConfigApi(f.session, f.config);

    const unwrapSpy = vi.spyOn(configCrypto, 'cekUnwrap');

    const adapter = new RemoteConfigAdapter(
      REMOTE,
      CONFIG_NAME,
      createTokenStorage({
        token: 'rct_1',
        wrappedCek: f.wrappedCek,
      }) as unknown as RemoteTokenStorage,
      createSecureStorage(toBase64(f.slotSecret))
    );

    const err = await adapter.pull().then(
      () => null,
      (e: unknown) => e
    );

    // The unwrap really did succeed, so this is not the stale-slot path.
    expect(unwrapSpy).toHaveBeenCalledTimes(1);
    await expect(unwrapSpy.mock.results[0]?.value).resolves.toBeDefined();
    expect(err).toBeInstanceOf(RemoteConfigUndecryptableError);
    expect(err).not.toBeInstanceOf(RemoteStaleSlotError);

    const message = (err as Error).message;
    // No raw WebCrypto text reaches the user.
    expect(message).not.toMatch(/operation-specific reason/i);
    // The identity of the thing that would not open, and a recovery step.
    expect(message).toContain(CONFIG_ID);
    expect(message).toContain(STORE_ID);
    expect(message).toMatch(/key slots|enrolled/i);
  });

  it('separates a session-layer failure from the store mismatch', async () => {
    // Same CEK on both sides, so the HMAC and the CEK layer both pass; only the
    // server-derived SDK layer is wrong. That is a retryable session problem,
    // not a store-identity problem, and it must not claim the latter.
    const f = await provision(PASSWORD);
    wireConfigApi({ ...f.session, sdk_derived: toBase64(randomBytes(32)) }, f.config);

    const adapter = new RemoteConfigAdapter(
      REMOTE,
      CONFIG_NAME,
      createTokenStorage({
        token: 'rct_1',
        wrappedCek: f.wrappedCek,
      }) as unknown as RemoteTokenStorage,
      createSecureStorage(toBase64(f.slotSecret))
    );

    const err = await adapter.pull().then(
      () => null,
      (e: unknown) => e
    );

    expect(err).toBeInstanceOf(RemoteConfigUndecryptableError);
    const message = (err as Error).message;
    expect(message).toContain(CONFIG_ID);
    expect(message).toMatch(/retry/i);
    expect(message).not.toContain(STORE_ID);
  });
});
