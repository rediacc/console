import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { RdcConfig } from '../../types/index.js';

// Mock global.fetch
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// Import after mock
const { VaultStoreAdapter } = await import('../vault-store-adapter.js');

/** Helper to create a successful Vault response */
function vaultResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  } as unknown as Response;
}

/** Helper to create a 404 response */
function vault404(): Response {
  return vaultResponse(404, { errors: [] });
}

const testConfig: RdcConfig = {
  id: 'test-uuid-1234',
  version: 3,
  machines: { prod: { ip: '10.0.0.1', user: 'root' } },
};

const testConfig2: RdcConfig = {
  id: 'test-uuid-5678',
  version: 1,
};

const defaultEntry = {
  name: 'test',
  type: 'vault' as const,
  vaultAddr: 'http://localhost:8200',
  vaultToken: 'test-token',
};

describe('VaultStoreAdapter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ============================================================================
  // Constructor
  // ============================================================================

  describe('constructor', () => {
    it('throws when vaultAddr is missing', () => {
      expect(
        () => new VaultStoreAdapter({ name: 'test', type: 'vault', vaultToken: 'tok' })
      ).toThrow('vaultAddr and vaultToken');
    });

    it('throws when vaultToken is missing', () => {
      expect(
        () =>
          new VaultStoreAdapter({ name: 'test', type: 'vault', vaultAddr: 'http://localhost:8200' })
      ).toThrow('vaultAddr and vaultToken');
    });

    it('uses defaults for mount and prefix', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      // Try a list to verify URL construction
      mockFetch.mockResolvedValue(vault404());
      await adapter.list();

      // Should use default mount "secret" and prefix "rdc/configs"
      const url = mockFetch.mock.calls[0][0] as string;
      expect(url).toContain('/v1/secret/metadata/rdc/configs');
    });
  });

  // ============================================================================
  // push()
  // ============================================================================

  describe('push()', () => {
    it('creates a new secret when config does not exist', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      // First call: GET (read existing) → 404
      // Second call: POST (write new) → 200
      mockFetch
        .mockResolvedValueOnce(vault404())
        .mockResolvedValueOnce(vaultResponse(200, { data: { version: 1 } }));

      const result = await adapter.push(testConfig, 'rediacc');
      expect(result.success).toBe(true);
      expect(result.remoteVersion).toBe(3);

      // Verify POST body
      const postCall = mockFetch.mock.calls[1];
      expect(postCall[1].method).toBe('POST');
      const body = JSON.parse(postCall[1].body);
      const stored = JSON.parse(body.data.config);
      expect(stored.id).toBe('test-uuid-1234');
      expect(stored.version).toBe(3);
    });

    it('updates existing secret when version is valid', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);
      const olderConfig = { ...testConfig, version: 2 };

      mockFetch
        .mockResolvedValueOnce(
          vaultResponse(200, { data: { data: { config: JSON.stringify(olderConfig) } } })
        )
        .mockResolvedValueOnce(vaultResponse(200, { data: { version: 2 } }));

      const result = await adapter.push(testConfig, 'rediacc');
      expect(result.success).toBe(true);
      expect(result.remoteVersion).toBe(3);
    });

    it('returns GUID mismatch error when remote has different id', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch.mockResolvedValueOnce(
        vaultResponse(200, { data: { data: { config: JSON.stringify(testConfig2) } } })
      );

      const result = await adapter.push(testConfig, 'rediacc');
      expect(result.success).toBe(false);
      expect(result.error).toContain('GUID mismatch');
    });

    it('returns version conflict when remote version is newer', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);
      const newerConfig = { ...testConfig, version: 10 };

      mockFetch.mockResolvedValueOnce(
        vaultResponse(200, { data: { data: { config: JSON.stringify(newerConfig) } } })
      );

      const result = await adapter.push(testConfig, 'rediacc');
      expect(result.success).toBe(false);
      expect(result.error).toContain('Version conflict');
    });

    it('returns error when Vault write fails', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch
        .mockResolvedValueOnce(vault404())
        .mockResolvedValueOnce(vaultResponse(403, { errors: ['permission denied'] }));

      const result = await adapter.push(testConfig, 'rediacc');
      expect(result.success).toBe(false);
      expect(result.error).toContain('403');
    });
  });

  // ============================================================================
  // pull()
  // ============================================================================

  describe('pull()', () => {
    it('returns config when secret exists', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch.mockResolvedValue(
        vaultResponse(200, { data: { data: { config: JSON.stringify(testConfig) } } })
      );

      const result = await adapter.pull('production');
      expect(result.success).toBe(true);
      expect(result.config?.id).toBe('test-uuid-1234');
      expect(result.config?.version).toBe(3);
    });

    it('returns not-found error when secret does not exist', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch.mockResolvedValue(vault404());

      const result = await adapter.pull('nonexistent');
      expect(result.success).toBe(false);
      expect(result.error).toContain('not found');
    });

    it('returns error when secret data contains invalid JSON', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch.mockResolvedValue(vaultResponse(200, { data: { data: { config: 'not-json' } } }));

      const result = await adapter.pull('broken');
      expect(result.success).toBe(false);
      expect(result.error).toContain('invalid JSON');
    });
  });

  // ============================================================================
  // list()
  // ============================================================================

  describe('list()', () => {
    it('returns sorted secret names', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch.mockResolvedValue(
        vaultResponse(200, { data: { keys: ['staging', 'production', 'rediacc'] } })
      );

      const result = await adapter.list();
      expect(result).toEqual(['production', 'rediacc', 'staging']);
    });

    it('returns empty array when no secrets exist', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch.mockResolvedValue(vault404());

      const result = await adapter.list();
      expect(result).toEqual([]);
    });

    it('filters out directory entries', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch.mockResolvedValue(
        vaultResponse(200, { data: { keys: ['production', 'subdir/', 'staging'] } })
      );

      const result = await adapter.list();
      expect(result).toEqual(['production', 'staging']);
    });
  });

  // ============================================================================
  // delete()
  // ============================================================================

  describe('delete()', () => {
    it('deletes existing secret and returns success', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch.mockResolvedValue(vaultResponse(204, null));

      const result = await adapter.delete('staging');
      expect(result.success).toBe(true);

      // Verify it uses metadata path and DELETE method
      const call = mockFetch.mock.calls[0];
      expect(call[0]).toContain('/metadata/');
      expect(call[1].method).toBe('DELETE');
    });

    it('returns error when secret does not exist', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch.mockResolvedValue(vault404());

      const result = await adapter.delete('nonexistent');
      expect(result.success).toBe(false);
      expect(result.error).toContain('not found');
    });
  });

  // ============================================================================
  // verify()
  // ============================================================================

  describe('verify()', () => {
    it('returns true when Vault is healthy and token is valid', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch
        .mockResolvedValueOnce(vaultResponse(200, { initialized: true, sealed: false }))
        .mockResolvedValueOnce(vaultResponse(200, { data: { id: 'test-token' } }));

      const result = await adapter.verify();
      expect(result).toBe(true);
    });

    it('returns false when Vault is sealed', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch.mockResolvedValue(vaultResponse(200, { initialized: true, sealed: true }));

      const result = await adapter.verify();
      expect(result).toBe(false);
    });

    it('returns false when token is invalid', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch
        .mockResolvedValueOnce(vaultResponse(200, { initialized: true, sealed: false }))
        .mockResolvedValueOnce(vaultResponse(403, { errors: ['permission denied'] }));

      const result = await adapter.verify();
      expect(result).toBe(false);
    });
  });

  // ============================================================================
  // Namespace header
  // ============================================================================

  describe('namespace header', () => {
    it('includes X-Vault-Namespace when set', async () => {
      const adapter = new VaultStoreAdapter({
        ...defaultEntry,
        vaultNamespace: 'admin/team-a',
      });

      mockFetch.mockResolvedValue(vault404());
      await adapter.list();

      const headers = mockFetch.mock.calls[0][1].headers;
      expect(headers['X-Vault-Namespace']).toBe('admin/team-a');
    });

    it('omits X-Vault-Namespace when not set', async () => {
      const adapter = new VaultStoreAdapter(defaultEntry);

      mockFetch.mockResolvedValue(vault404());
      await adapter.list();

      const headers = mockFetch.mock.calls[0][1].headers;
      expect(headers['X-Vault-Namespace']).toBeUndefined();
    });
  });
});
