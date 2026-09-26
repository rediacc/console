import type { RdcConfig } from '@rediacc/shared/config-schema';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// ─── Hoisted Mocks ──────────────────────────────────────────────────────

const {
  mockConfigServerFetch,
  mockSelectiveDecrypt,
  mockSelectiveEncrypt,
  mockDeriveWrappingKey,
  mockCekUnwrap,
  mockImportAesKey,
  mockFromBase64,
} = vi.hoisted(() => ({
  mockConfigServerFetch: vi.fn(),
  mockSelectiveDecrypt: vi.fn(),
  mockSelectiveEncrypt: vi.fn(),
  mockDeriveWrappingKey: vi.fn(),
  mockCekUnwrap: vi.fn(),
  mockImportAesKey: vi.fn(),
  mockFromBase64: vi.fn(),
}));

vi.mock('../../services/config/config-server-client.js', () => ({
  configServerFetch: mockConfigServerFetch,
  ConfigServerError: class ConfigServerError extends Error {
    status: number;
    code?: string;
    constructor(message: string, status: number, code?: string) {
      super(message);
      this.name = 'ConfigServerError';
      this.status = status;
      this.code = code;
    }
  },
}));

vi.mock('@rediacc/shared/config-crypto', () => ({
  ENVELOPE_VERSION: 3,
  derivePointerBlindingKey: vi.fn(() => Promise.resolve({})),
  blindPointer: vi.fn((_key: unknown, pointer: string) => Promise.resolve(`blind:${pointer}`)),
  selectiveDecrypt: mockSelectiveDecrypt,
  selectiveEncrypt: mockSelectiveEncrypt,
  deriveWrappingKey: mockDeriveWrappingKey,
  cekUnwrap: mockCekUnwrap,
  importAesKey: mockImportAesKey,
  fromBase64: mockFromBase64,
}));

import type { RemoteConfig } from '../../types/index.js';
import {
  isNetworkError,
  RemoteAuthError,
  RemoteConfigAdapter,
  RemotePasskeySecretMissingError,
  RemotePreconditionError,
  RemoteRollbackError,
  RemoteStaleSlotError,
  RemoteTokenExpiredError,
  RemoteTokenIpMismatchError,
  RemoteUnreachableError,
  RemoteVersionConflictError,
} from '../remote-config-adapter.js';
import type { RemoteTokenStorage } from '../remote-token-storage.js';

// ─── Test Fixtures ───────────────────────────────────────────────────────

const REMOTE: RemoteConfig = {
  apiUrl: 'https://account.example.com',
  storeId: 'store-001',
  configId: 'config-001',
  teamId: 'team-001',
  storageKeyId: 'key-001',
};

const CONFIG_NAME = 'test-config';

/** What the (mocked) sealing step returns: a v3 envelope with its commitment salt. */
const SEALED_ENVELOPE = {
  envelopeVersion: 3,
  id: 'cfg-id',
  version: 6,
  sdkEpoch: 10,
  commitments: { alg: 'HMAC-SHA256', fckSalt: 'fresh-salt', fields: {} },
};

/** A pull response body: the blob plus the session material it carries. */
function pullBody() {
  return {
    server_secret: 'c2Vy',
    sdk_derived: 'c2Rr',
    configData: 'blob',
    envelope: {
      envelopeVersion: 3,
      configId: 'c',
      version: 1,
      teamId: null,
      lastModified: 'x',
      sdkEpoch: 1,
      commitments: { alg: 'HMAC-SHA256', fckSalt: 'salt', fields: {} },
    },
    hmac: null,
  };
}

/**
 * The lease reads through `get` and records every persisted rotation through `updateToken`, so a
 * test sees which token each request sent and which ones were saved.
 */
function createMockTokenStorage() {
  const storage = {
    get: vi.fn(),
    set: vi.fn(),
    updateToken: vi.fn(),
    recordSync: vi.fn(),
    delete: vi.fn(),
    withLease: vi.fn(
      async (
        name: string,
        fn: (lease: {
          data: { token: string; wrappedCek: string } | null;
          token: string | undefined;
          sync: unknown;
          update(token: string): Promise<void>;
          recordSync(record: unknown): Promise<void>;
        }) => Promise<unknown>
      ) => {
        const data = (await storage.get(name)) as {
          token: string;
          wrappedCek: string;
          sync?: unknown;
        } | null;
        let current = data;
        return fn({
          data,
          get token() {
            return current?.token;
          },
          get sync() {
            return current?.sync;
          },
          update: async (token: string) => {
            current = current ? { ...current, token } : current;
            await storage.updateToken(name, token);
          },
          recordSync: async (sync: unknown) => {
            current = current ? { ...current, sync } : current;
            await storage.recordSync(name, sync);
          },
        });
      }
    ),
  };
  return storage;
}

function createMockSecureStorage() {
  return {
    get: vi.fn(),
    set: vi.fn(),
    delete: vi.fn(),
    type: 'mock',
  };
}

describe('RemoteConfigAdapter', () => {
  let tokenStorage: ReturnType<typeof createMockTokenStorage>;
  let secureStorage: ReturnType<typeof createMockSecureStorage>;
  let adapter: RemoteConfigAdapter;

  beforeEach(() => {
    vi.clearAllMocks();

    tokenStorage = createMockTokenStorage();
    secureStorage = createMockSecureStorage();
    adapter = new RemoteConfigAdapter(
      REMOTE,
      CONFIG_NAME,
      tokenStorage as unknown as RemoteTokenStorage,
      secureStorage
    );

    // Default: token storage returns valid token + wrappedCek
    tokenStorage.get.mockResolvedValue({ token: 'tok_current', wrappedCek: 'wrapped_cek_b64' });

    // Default: secure storage returns passkey secret
    secureStorage.get.mockResolvedValue('passkey_secret_b64');

    // Default: crypto mocks
    mockFromBase64.mockReturnValue(new Uint8Array([1, 2, 3]));
    mockImportAesKey.mockResolvedValue({ type: 'secret', algorithm: 'AES-GCM' });
    mockDeriveWrappingKey.mockResolvedValue({ type: 'wrapping-key' });
    mockCekUnwrap.mockResolvedValue({ type: 'cek-key' });
  });

  // ─── pull() ──────────────────────────────────────────────────────────

  describe('pull', () => {
    it('decrypts with the key the PULL returns (the push epoch), not the session key of the current epoch', async () => {
      // 2026-09-25: after the first remote enable every later pull failed with "the server session layer would not open it": the blob is sealed under the epoch it was pushed in, and the pull response carries that epoch's sdk_derived, which the CLI ignored.
      mockFromBase64.mockImplementation((b64: string) => new TextEncoder().encode(String(b64)));
      mockImportAesKey.mockImplementation((bytes: Uint8Array) =>
        Promise.resolve({ marker: new TextDecoder().decode(bytes) })
      );
      mockConfigServerFetch.mockResolvedValueOnce({
        data: {
          server_secret: 'c2Vy',
          configData: 'encrypted-blob',
          envelope: {
            envelopeVersion: 3,
            commitments: { alg: 'HMAC-SHA256', fckSalt: 's', fields: {} },
            configId: 'config-001',
            version: 3,
            teamId: null,
            lastModified: 'x',
            sdkEpoch: 7,
          },
          hmac: 'hmac-value',
          sdk_derived: 'PUSH_EPOCH_KEY',
        },
      });
      mockSelectiveDecrypt.mockResolvedValue({
        id: 'c',
        version: 3,
        machines: {},
        repositories: {},
        storages: {},
        ssh: null,
      });

      const result = await adapter.pull();

      const [payload, , sdkKey] = mockSelectiveDecrypt.mock.calls.at(-1) as [
        { envelope: { sdkEpoch: number } },
        unknown,
        { marker: string },
      ];
      expect(sdkKey.marker).toBe('PUSH_EPOCH_KEY');
      expect(payload.envelope.sdkEpoch).toBe(7);
      expect(result.sdkEpoch).toBe(7);
    });

    it('should pull in ONE request (server_secret rides the pull), decrypt, and return result', async () => {
      // Config endpoint: the only request (F8: /session would spend a second token use)
      mockConfigServerFetch.mockResolvedValueOnce({
        data: {
          server_secret: 'c2VydmVyX3NlY3JldA==',
          sdk_derived: 'c2RrX2Rlcml2ZWQ=',
          configData: 'encrypted-blob',
          envelope: {
            envelopeVersion: 3,
            commitments: { alg: 'HMAC-SHA256', fckSalt: 's', fields: {} },
            configId: 'config-001',
            version: 5,
            teamId: 'team-001',
            lastModified: '2025-01-01T00:00:00Z',
            sdkEpoch: 42,
          },
          hmac: 'hmac-value',
        },
      });

      // Decrypted result
      mockSelectiveDecrypt.mockResolvedValue({
        id: 'cfg-id-123',
        version: 5,
        machines: { prod: { ip: '10.0.0.1', user: 'root' } },
        repositories: {},
        storages: {},
        ssh: null,
      });

      const result = await adapter.pull();

      expect(result.config.id).toBe('cfg-id-123');
      expect(result.config.resources?.machines).toHaveProperty('prod');
      expect(result.version).toBe(5);
      expect(result.sdkEpoch).toBe(42);

      expect(mockConfigServerFetch).toHaveBeenCalledTimes(1);
      expect(mockConfigServerFetch).toHaveBeenCalledWith(
        '/account/api/v1/configs/config-001?teamId=team-001',
        expect.objectContaining({ configToken: 'tok_current' })
      );
    });

    it('should persist the rotated token from the pull response', async () => {
      mockConfigServerFetch.mockResolvedValueOnce({
        data: {
          server_secret: 'c2Vy',
          sdk_derived: 'c2Rr',
          configData: 'blob',
          envelope: {
            envelopeVersion: 3,
            commitments: { alg: 'HMAC-SHA256', fckSalt: 's', fields: {} },
            configId: 'c',
            version: 1,
            teamId: null,
            lastModified: '2025-01-01T00:00:00Z',
          },
          hmac: null,
        },
        newServerToken: 'tok_rotated_1',
      });

      mockSelectiveDecrypt.mockResolvedValue({
        id: 'id',
        version: 1,
        machines: {},
        repositories: {},
        storages: {},
      });

      await adapter.pull();

      expect(tokenStorage.updateToken).toHaveBeenCalledWith(CONFIG_NAME, 'tok_rotated_1');
      expect(tokenStorage.withLease).toHaveBeenCalledTimes(1);
    });

    it('persists the token an ERROR response rotated to before classifying the error (F9)', async () => {
      const { ConfigServerError } = await import('../../services/config/config-server-client.js');
      mockConfigServerFetch.mockRejectedValueOnce(
        Object.assign(new ConfigServerError('Config not found', 404), {
          newServerToken: 'tok_after_error',
        })
      );

      await expect(adapter.pull()).rejects.toBeInstanceOf(ConfigServerError);
      expect(tokenStorage.updateToken).toHaveBeenCalledWith(CONFIG_NAME, 'tok_after_error');
    });

    it('should throw RemoteTokenExpiredError on 401 token_expired', async () => {
      const { ConfigServerError } = await import('../../services/config/config-server-client.js');
      mockConfigServerFetch.mockRejectedValueOnce(
        new ConfigServerError('Config auth failed: token_expired', 401)
      );

      await expect(adapter.pull()).rejects.toThrow(RemoteTokenExpiredError);
    });

    // A 401 keeps the server's reason: ip_mismatch is NOT an expired token, and reading it as one sent the user in a loop (the relay handoff bug).
    it('should throw RemoteTokenIpMismatchError on 401 ip_mismatch, not an expiry', async () => {
      const { ConfigServerError } = await import('../../services/config/config-server-client.js');
      mockConfigServerFetch.mockRejectedValueOnce(
        new ConfigServerError('Config auth failed: ip_mismatch', 401)
      );

      const err = await adapter.pull().catch((e: unknown) => e);
      expect(err).toBeInstanceOf(RemoteTokenIpMismatchError);
      expect(err).not.toBeInstanceOf(RemoteTokenExpiredError);
      expect((err as RemoteAuthError).reason).toBe('ip_mismatch');
      expect((err as Error).message).toContain('rdc config remote enable');
      expect((err as Error).message).not.toBe(new RemoteTokenExpiredError().message);
    });

    it.each([
      ['token_exhausted', 'token_exhausted'],
      ['invalid_token', 'invalid_token'],
      ['decryption_failed', 'decryption_failed'],
    ])('should keep reason %s on a 401 with its own message', async (serverReason, reason) => {
      const { ConfigServerError } = await import('../../services/config/config-server-client.js');
      mockConfigServerFetch.mockRejectedValueOnce(
        new ConfigServerError(`Config auth failed: ${serverReason}`, 401)
      );

      const err = await adapter.pull().catch((e: unknown) => e);
      expect(err).toBeInstanceOf(RemoteAuthError);
      expect(err).not.toBeInstanceOf(RemoteTokenExpiredError);
      expect((err as RemoteAuthError).reason).toBe(reason);
      expect((err as Error).message).not.toBe(new RemoteTokenExpiredError().message);
    });

    it('should carry an unrecognized 401 verbatim rather than calling it expired', async () => {
      const { ConfigServerError } = await import('../../services/config/config-server-client.js');
      mockConfigServerFetch.mockRejectedValueOnce(
        new ConfigServerError('Config token required (X-Config-Token header)', 401)
      );

      const err = await adapter.pull().catch((e: unknown) => e);
      expect(err).toBeInstanceOf(RemoteAuthError);
      expect(err).not.toBeInstanceOf(RemoteTokenExpiredError);
      expect((err as RemoteAuthError).reason).toBe('unauthorized');
      expect((err as Error).message).toContain('Config token required (X-Config-Token header)');
    });

    it('should throw RemotePasskeySecretMissingError when passkey_secret is missing', async () => {
      mockConfigServerFetch.mockResolvedValueOnce({ data: pullBody() });

      // Passkey secret not found
      secureStorage.get.mockResolvedValue(null);

      await expect(adapter.pull()).rejects.toThrow(RemotePasskeySecretMissingError);
    });

    it('should throw RemoteTokenExpiredError when token storage is empty', async () => {
      tokenStorage.get.mockResolvedValue(null);

      await expect(adapter.pull()).rejects.toThrow(RemoteTokenExpiredError);
    });

    it('should throw RemoteStaleSlotError when the CEK unwrap fails (rotated/stale slot)', async () => {
      // The pull succeeds so we reach the CEK-derivation step.
      mockConfigServerFetch.mockResolvedValueOnce({ data: pullBody() });

      // A wrong slot secret / rotated CEK surfaces as an AES-GCM auth failure.
      mockCekUnwrap.mockRejectedValueOnce(new Error('OperationError'));

      await expect(adapter.pull()).rejects.toThrow(RemoteStaleSlotError);
    });
  });

  // ─── push() ──────────────────────────────────────────────────────────

  describe('push', () => {
    it('should encrypt and call PUT endpoint', async () => {
      // Session
      mockConfigServerFetch.mockResolvedValueOnce({
        data: { server_secret: 'c2Vy', sdk_derived: 'c2Rr', sdkEpoch: 10 },
      });

      // Encrypt result
      mockSelectiveEncrypt.mockResolvedValue({
        encryptedBlob: 'encrypted-data',
        envelope: SEALED_ENVELOPE,
      });

      // Push response
      mockConfigServerFetch.mockResolvedValueOnce({
        data: { version: 6 },
      });

      const config: RdcConfig = {
        schemaVersion: 3,
        id: 'cfg-id',
        version: 5,
        machines: { m1: { ip: '10.0.0.1', user: 'root' } },
      };

      const result = await adapter.push(config, 5);

      expect(result.version).toBe(6);
      expect(mockSelectiveEncrypt).toHaveBeenCalled();

      // PUT call should include encrypted data
      expect(mockConfigServerFetch).toHaveBeenCalledWith(
        '/account/api/v1/configs/config-001',
        expect.objectContaining({
          method: 'PUT',
          body: expect.objectContaining({
            teamId: 'team-001',
            version: 6,
            encryptedBlob: 'encrypted-data',
            envelope: SEALED_ENVELOPE,
            sdkEpoch: 10,
          }),
        })
      );
    });

    it('should persist rotated tokens during push', async () => {
      mockConfigServerFetch.mockResolvedValueOnce({
        data: { server_secret: 'c2Vy', sdk_derived: 'c2Rr', sdkEpoch: 1 },
        newServerToken: 'tok_push_rotated',
      });

      mockSelectiveEncrypt.mockResolvedValue({ encryptedBlob: 'e', envelope: SEALED_ENVELOPE });

      mockConfigServerFetch.mockResolvedValueOnce({
        data: { version: 2 },
      });

      await adapter.push({ schemaVersion: 3, id: 'id', version: 1 }, 1);

      expect(tokenStorage.updateToken).toHaveBeenCalledWith(CONFIG_NAME, 'tok_push_rotated');
      // The PUT sends the token /session rotated to, in the same lease (F8).
      expect(mockConfigServerFetch.mock.calls[0][1]).toMatchObject({ configToken: 'tok_current' });
      expect(mockConfigServerFetch.mock.calls[1][1]).toMatchObject({
        configToken: 'tok_push_rotated',
      });
      expect(tokenStorage.withLease).toHaveBeenCalledTimes(1);
    });
  });

  // ─── error taxonomy ──────────────────────────────────────────────────

  describe('error taxonomy', () => {
    it('should throw RemoteVersionConflictError carrying the server 409 message verbatim', async () => {
      const { ConfigServerError } = await import('../../services/config/config-server-client.js');
      // Session succeeds; the PUT then conflicts.
      mockConfigServerFetch.mockResolvedValueOnce({
        data: { server_secret: 'c2Vy', sdk_derived: 'c2Rr', sdkEpoch: 1 },
      });
      mockSelectiveEncrypt.mockResolvedValue({ encryptedBlob: 'e', envelope: SEALED_ENVELOPE });
      mockConfigServerFetch.mockRejectedValueOnce(
        new ConfigServerError('Version conflict: current version is 7', 409)
      );

      const err = await adapter.push({ schemaVersion: 3, id: 'id', version: 1 }, 1).then(
        () => null,
        (e: unknown) => e
      );
      expect(err).toBeInstanceOf(RemoteVersionConflictError);
      expect((err as Error).message).toBe('Version conflict: current version is 7');
    });

    it('should wrap a fetch network failure into RemoteUnreachableError naming the apiUrl', async () => {
      mockConfigServerFetch.mockRejectedValueOnce(
        new TypeError('fetch failed', { cause: { code: 'ECONNREFUSED' } })
      );

      const err = await adapter.pull().then(
        () => null,
        (e: unknown) => e
      );
      expect(err).toBeInstanceOf(RemoteUnreachableError);
      expect((err as RemoteUnreachableError).apiUrl).toBe(REMOTE.apiUrl);
      expect((err as Error).message).toContain(REMOTE.apiUrl);
    });

    it('should wrap a 5xx ConfigServerError into RemoteUnreachableError', async () => {
      const { ConfigServerError } = await import('../../services/config/config-server-client.js');
      mockConfigServerFetch.mockRejectedValueOnce(new ConfigServerError('Bad gateway', 502));

      await expect(adapter.pull()).rejects.toBeInstanceOf(RemoteUnreachableError);
    });

    it('should surface a 404 unchanged as ConfigServerError (the seed path branches on it)', async () => {
      const { ConfigServerError } = await import('../../services/config/config-server-client.js');
      // The config GET 404s (fresh store, nothing pushed yet).
      mockConfigServerFetch.mockRejectedValueOnce(new ConfigServerError('Config not found', 404));

      const err = await adapter.pull().then(
        () => null,
        (e: unknown) => e
      );
      expect(err).toBeInstanceOf(ConfigServerError);
      expect((err as { status: number }).status).toBe(404);
      expect(err).not.toBeInstanceOf(RemoteUnreachableError);
    });
  });

  describe('isNetworkError', () => {
    it('classifies fetch TypeErrors and known socket codes, walking cause chains', () => {
      expect(isNetworkError(new TypeError('fetch failed'))).toBe(true);
      expect(isNetworkError({ code: 'ECONNREFUSED' })).toBe(true);
      expect(isNetworkError({ code: 'UND_ERR_CONNECT_TIMEOUT' })).toBe(true);
      // Nested one level deeper, as undici does.
      expect(isNetworkError(new Error('outer', { cause: { code: 'ETIMEDOUT' } }))).toBe(true);
      expect(
        isNetworkError(
          new Error('outer', { cause: new Error('mid', { cause: { code: 'EPIPE' } }) })
        )
      ).toBe(true);
    });

    it('does not classify semantic/auth failures as network errors', () => {
      expect(isNetworkError(new Error('plain'))).toBe(false);
      expect(isNetworkError(new TypeError('undefined is not a function'))).toBe(false);
      expect(isNetworkError({ code: 'SOMETHING_ELSE' })).toBe(false);
      expect(isNetworkError(null)).toBe(false);
    });
  });

  // ─── testConnection() ────────────────────────────────────────────────

  describe('testConnection', () => {
    it('should return true on success', async () => {
      mockConfigServerFetch.mockResolvedValueOnce({
        data: { server_secret: 'c2Vy', sdk_derived: 'c2Rr', sdkEpoch: 1 },
      });

      const result = await adapter.testConnection();
      expect(result).toBe(true);
    });

    it('should return false on failure', async () => {
      mockConfigServerFetch.mockRejectedValueOnce(new Error('Network error'));

      const result = await adapter.testConnection();
      expect(result).toBe(false);
    });

    it('should return false when token is missing', async () => {
      tokenStorage.get.mockResolvedValue(null);

      const result = await adapter.testConnection();
      expect(result).toBe(false);
    });
  });
  // ─── envelope v3: high-water mark, v2 read, tombstones (T8/T9) ──────────

  describe('envelope v3 guards', () => {
    const BINDING = 'store-001/config-001/team-001';
    const seen = (highWater: number, envelopeVersion: 2 | 3 = 3) => ({
      binding: BINDING,
      highWater,
      envelopeVersion,
      fckSalt: 'stored-salt',
    });
    const pulledAt = (version: number, envelopeVersion: 2 | 3 = 3) => ({
      data: {
        ...pullBody(),
        envelope: { ...pullBody().envelope, version, envelopeVersion },
      },
    });

    beforeEach(() => {
      mockSelectiveDecrypt.mockResolvedValue({ id: 'c', version: 1, machines: {} });
    });

    it('refuses a pull older than the version this device already saw (RemoteRollbackError)', async () => {
      tokenStorage.get.mockResolvedValue({ token: 't', wrappedCek: 'w', sync: seen(5) });
      mockConfigServerFetch.mockResolvedValueOnce(pulledAt(3));
      await expect(adapter.pull()).rejects.toBeInstanceOf(RemoteRollbackError);
      expect(tokenStorage.recordSync).not.toHaveBeenCalled();
    });

    it('refuses the v2 envelope once the device has seen v3 for this config', async () => {
      tokenStorage.get.mockResolvedValue({ token: 't', wrappedCek: 'w', sync: seen(5) });
      mockConfigServerFetch.mockResolvedValueOnce(pulledAt(6, 2));
      await expect(adapter.pull()).rejects.toBeInstanceOf(RemoteRollbackError);
    });

    it('ignores a record that names another config', async () => {
      tokenStorage.get.mockResolvedValue({
        token: 't',
        wrappedCek: 'w',
        sync: { ...seen(9), binding: 'other/config/' },
      });
      mockConfigServerFetch.mockResolvedValueOnce(pulledAt(2));
      await expect(adapter.pull()).resolves.toMatchObject({ version: 2 });
    });

    it('reads a v2 store with a warning, and records it for the upgrading push', async () => {
      const { outputService } = await import('../../services/core/output.js');
      const warn = vi.spyOn(outputService, 'warn').mockImplementation(() => undefined);
      mockConfigServerFetch.mockResolvedValueOnce(pulledAt(4, 2));
      await adapter.pull();
      expect(warn).toHaveBeenCalledTimes(1);
      expect(tokenStorage.recordSync).toHaveBeenCalledWith(CONFIG_NAME, {
        binding: BINDING,
        highWater: 4,
        envelopeVersion: 2,
        fckSalt: 'salt',
      });
      warn.mockRestore();
    });

    it('a push from the version the device saw carries that envelope as its prior, and moves the mark', async () => {
      tokenStorage.get.mockResolvedValue({ token: 't', wrappedCek: 'w', sync: seen(5, 2) });
      mockConfigServerFetch.mockResolvedValueOnce({
        data: { server_secret: 'c2Vy', sdk_derived: 'c2Rr', sdkEpoch: 10 },
      });
      mockSelectiveEncrypt.mockResolvedValue({ encryptedBlob: 'e', envelope: SEALED_ENVELOPE });
      mockConfigServerFetch.mockResolvedValueOnce({ data: { version: 6 } });

      await adapter.push({ schemaVersion: 3, id: 'cfg-id', version: 5 }, 5);

      const options = mockSelectiveEncrypt.mock.calls.at(-1)?.[3] as {
        prior?: { envelopeVersion: number; fckSalt: string };
        storeId: string;
      };
      expect(options.storeId).toBe('store-001');
      expect(options.prior).toMatchObject({ envelopeVersion: 2, fckSalt: 'stored-salt' });
      expect(tokenStorage.recordSync).toHaveBeenCalledWith(CONFIG_NAME, {
        binding: BINDING,
        highWater: 6,
        envelopeVersion: 3,
        fckSalt: 'fresh-salt',
      });
    });

    it('a 409 precondition_failed is RemotePreconditionError naming the pointers, not a version conflict', async () => {
      const { ConfigServerError } = await import('../../services/config/config-server-client.js');
      mockConfigServerFetch.mockResolvedValueOnce({
        data: { server_secret: 'c2Vy', sdk_derived: 'c2Rr', sdkEpoch: 1 },
      });
      mockSelectiveEncrypt.mockResolvedValue({ encryptedBlob: 'e', envelope: SEALED_ENVELOPE });
      const refusal = new ConfigServerError('Precondition failed', 409, 'precondition_failed');
      (refusal as { mismatchedPaths?: string[] }).mismatchedPaths = [
        'blind:/resources/machines/m1/ip',
        'opaque-key',
      ];
      mockConfigServerFetch.mockRejectedValueOnce(refusal);

      const base: RdcConfig = {
        schemaVersion: 3,
        id: 'cfg-id',
        version: 1,
        resources: { machines: { m1: { ip: '10.0.0.1', user: 'root' } } },
      };
      const err = await adapter
        .push({ schemaVersion: 3, id: 'cfg-id', version: 1 }, 1, { base })
        .then(
          () => null,
          (e: unknown) => e
        );
      expect(err).toBeInstanceOf(RemotePreconditionError);
      expect(err).not.toBeInstanceOf(RemoteVersionConflictError);
      expect((err as RemotePreconditionError).paths).toEqual([
        '/resources/machines/m1/ip',
        'opaque-key',
      ]);
    });
  });
});
