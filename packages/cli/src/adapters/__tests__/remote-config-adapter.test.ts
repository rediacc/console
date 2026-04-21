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

vi.mock('../../services/config-server-client.js', () => ({
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

vi.mock('@rediacc/shared/config-crypto', () => ({
  selectiveDecrypt: mockSelectiveDecrypt,
  selectiveEncrypt: mockSelectiveEncrypt,
  deriveWrappingKey: mockDeriveWrappingKey,
  cekUnwrap: mockCekUnwrap,
  importAesKey: mockImportAesKey,
  fromBase64: mockFromBase64,
}));

import type { RemoteConfig } from '../../types/index.js';
import {
  RemoteConfigAdapter,
  RemotePasskeySecretMissingError,
  RemoteTokenExpiredError,
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

function createMockTokenStorage() {
  return {
    get: vi.fn(),
    set: vi.fn(),
    updateToken: vi.fn(),
    delete: vi.fn(),
  };
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
    it('should fetch session, fetch config, decrypt, and return result', async () => {
      // Session endpoint
      mockConfigServerFetch.mockResolvedValueOnce({
        data: {
          server_secret: 'c2VydmVyX3NlY3JldA==',
          sdk_derived: 'c2RrX2Rlcml2ZWQ=',
          sdkEpoch: 42,
        },
      });

      // Config endpoint
      mockConfigServerFetch.mockResolvedValueOnce({
        data: {
          configData: 'encrypted-blob',
          envelope: {
            configId: 'config-001',
            version: 5,
            teamId: 'team-001',
            lastModified: '2025-01-01T00:00:00Z',
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
      expect(result.config.machines).toHaveProperty('prod');
      expect(result.version).toBe(5);
      expect(result.sdkEpoch).toBe(42);

      // Session endpoint called first
      expect(mockConfigServerFetch).toHaveBeenCalledWith(
        '/account/api/v1/configs/session',
        expect.objectContaining({ method: 'POST', configToken: 'tok_current' })
      );

      // Config endpoint called second
      expect(mockConfigServerFetch).toHaveBeenCalledWith(
        '/account/api/v1/configs/config-001?teamId=team-001',
        expect.objectContaining({ configToken: 'tok_current' })
      );
    });

    it('should persist rotated tokens from server responses', async () => {
      // Session returns a rotated token
      mockConfigServerFetch.mockResolvedValueOnce({
        data: { server_secret: 'c2Vy', sdk_derived: 'c2Rr', sdkEpoch: 1 },
        newServerToken: 'tok_rotated_1',
      });

      // Config also returns a rotated token
      mockConfigServerFetch.mockResolvedValueOnce({
        data: {
          configData: 'blob',
          envelope: {
            configId: 'c',
            version: 1,
            teamId: null,
            lastModified: '2025-01-01T00:00:00Z',
          },
          hmac: null,
        },
        newServerToken: 'tok_rotated_2',
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
      expect(tokenStorage.updateToken).toHaveBeenCalledWith(CONFIG_NAME, 'tok_rotated_2');
    });

    it('should throw RemoteTokenExpiredError on 401', async () => {
      const { ConfigServerError } = await import('../../services/config-server-client.js');
      mockConfigServerFetch.mockRejectedValueOnce(new ConfigServerError('Unauthorized', 401));

      await expect(adapter.pull()).rejects.toThrow(RemoteTokenExpiredError);
    });

    it('should throw RemotePasskeySecretMissingError when passkey_secret is missing', async () => {
      // Session succeeds
      mockConfigServerFetch.mockResolvedValueOnce({
        data: { server_secret: 'c2Vy', sdk_derived: 'c2Rr', sdkEpoch: 1 },
      });

      // Passkey secret not found
      secureStorage.get.mockResolvedValue(null);

      await expect(adapter.pull()).rejects.toThrow(RemotePasskeySecretMissingError);
    });

    it('should throw RemoteTokenExpiredError when token storage is empty', async () => {
      tokenStorage.get.mockResolvedValue(null);

      await expect(adapter.pull()).rejects.toThrow(RemoteTokenExpiredError);
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
        hmac: 'hmac-data',
      });

      // Push response
      mockConfigServerFetch.mockResolvedValueOnce({
        data: { version: 6 },
      });

      const config = {
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
            hmac: 'hmac-data',
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

      mockSelectiveEncrypt.mockResolvedValue({ encryptedBlob: 'e', hmac: 'h' });

      mockConfigServerFetch.mockResolvedValueOnce({
        data: { version: 2 },
      });

      await adapter.push({ id: 'id', version: 1 }, 1);

      expect(tokenStorage.updateToken).toHaveBeenCalledWith(CONFIG_NAME, 'tok_push_rotated');
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
});
