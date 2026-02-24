import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import type { RdcConfig } from '../../types/index.js';

// Mock execFile to simulate bw CLI
const mockExecFile = vi.fn();
vi.mock('node:child_process', () => ({
  execFile: mockExecFile,
}));

// Import after mock
const { BitwardenStoreAdapter } = await import('../bitwarden-store-adapter.js');

/** Helper to create a mock bw response */
function mockBwResponse(stdout: string) {
  return (
    _cmd: string,
    _args: string[],
    _opts: unknown,
    cb: (err: null, res: { stdout: string }) => void
  ) => {
    cb(null, { stdout });
  };
}

/** Helper to create a mock bw error */
function mockBwError(message: string) {
  return (_cmd: string, _args: string[], _opts: unknown, cb: (err: Error) => void) => {
    cb(new Error(message));
  };
}

/** Build a BW status response */
function bwStatus(status: 'unauthenticated' | 'locked' | 'unlocked') {
  return JSON.stringify({ status, userEmail: 'test@example.com' });
}

/** Build a BW item (secure note) */
function bwItem(id: string, name: string, notes: string | null, folderId: string | null = null) {
  return { id, name, notes, type: 2, secureNote: { type: 0 }, folderId };
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

describe('BitwardenStoreAdapter', () => {
  let savedBwSession: string | undefined;

  beforeEach(() => {
    vi.clearAllMocks();
    savedBwSession = process.env.BW_SESSION;
    process.env.BW_SESSION = 'test-session-key';
  });

  afterEach(() => {
    if (savedBwSession === undefined) {
      delete process.env.BW_SESSION;
    } else {
      process.env.BW_SESSION = savedBwSession;
    }
  });

  // ============================================================================
  // Session Management
  // ============================================================================

  describe('session management', () => {
    it('uses BW_SESSION env var when set', async () => {
      process.env.BW_SESSION = 'my-session';
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });

      mockExecFile.mockImplementation(mockBwResponse(JSON.stringify([])));

      await adapter.list();

      // Should pass --session with the env var value
      const call = mockExecFile.mock.calls[0];
      expect(call[1]).toContain('--session');
      expect(call[1]).toContain('my-session');
    });

    it('throws descriptive error when vault is locked', async () => {
      delete process.env.BW_SESSION;
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });

      // First call is status check
      mockExecFile.mockImplementation(mockBwResponse(bwStatus('locked')));

      await expect(adapter.list()).rejects.toThrow('vault is locked');
    });

    it('throws descriptive error when not logged in', async () => {
      delete process.env.BW_SESSION;
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });

      mockExecFile.mockImplementation(mockBwResponse(bwStatus('unauthenticated')));

      await expect(adapter.list()).rejects.toThrow('not logged in');
    });

    it('throws when bw CLI is not installed', async () => {
      delete process.env.BW_SESSION;
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });

      mockExecFile.mockImplementation(mockBwError('spawn bw ENOENT'));

      await expect(adapter.list()).rejects.toThrow('Bitwarden CLI');
    });
  });

  // ============================================================================
  // push()
  // ============================================================================

  describe('push()', () => {
    it('creates a new secure note when config does not exist', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });

      // First call: list items (find) → empty
      // Second call: create item
      mockExecFile.mockImplementation(
        (
          _cmd: string,
          args: string[],
          _opts: unknown,
          cb: (err: null, res: { stdout: string }) => void
        ) => {
          if (args.includes('list')) {
            cb(null, { stdout: JSON.stringify([]) });
          } else if (args.includes('create')) {
            // Verify the base64-encoded item
            const encoded = args[args.indexOf('create') + 2];
            const decoded = JSON.parse(Buffer.from(encoded, 'base64').toString());
            expect(decoded.type).toBe(2);
            expect(decoded.name).toBe('rdc:rediacc');
            expect(decoded.secureNote).toEqual({ type: 0 });
            const notes = JSON.parse(decoded.notes);
            expect(notes.id).toBe('test-uuid-1234');
            cb(null, { stdout: '{}' });
          } else {
            cb(null, { stdout: '' });
          }
        }
      );

      const result = await adapter.push(testConfig, 'rediacc');
      expect(result.success).toBe(true);
      expect(result.remoteVersion).toBe(3);
    });

    it('updates existing item when config exists and version is valid', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });
      const existingItem = bwItem(
        'item-id-1',
        'rdc:rediacc',
        JSON.stringify({ ...testConfig, version: 2 })
      );

      mockExecFile.mockImplementation(
        (
          _cmd: string,
          args: string[],
          _opts: unknown,
          cb: (err: null, res: { stdout: string }) => void
        ) => {
          if (args.includes('list')) {
            cb(null, { stdout: JSON.stringify([existingItem]) });
          } else if (args.includes('edit')) {
            expect(args).toContain('item-id-1');
            cb(null, { stdout: '{}' });
          } else {
            cb(null, { stdout: '' });
          }
        }
      );

      const result = await adapter.push(testConfig, 'rediacc');
      expect(result.success).toBe(true);
      expect(result.remoteVersion).toBe(3);
    });

    it('returns GUID mismatch error when remote has different id', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });
      const existingItem = bwItem('item-id-1', 'rdc:rediacc', JSON.stringify(testConfig2));

      mockExecFile.mockImplementation(
        (
          _cmd: string,
          args: string[],
          _opts: unknown,
          cb: (err: null, res: { stdout: string }) => void
        ) => {
          if (args.includes('list')) {
            cb(null, { stdout: JSON.stringify([existingItem]) });
          } else {
            cb(null, { stdout: '' });
          }
        }
      );

      const result = await adapter.push(testConfig, 'rediacc');
      expect(result.success).toBe(false);
      expect(result.error).toContain('GUID mismatch');
    });

    it('returns version conflict when remote version is newer', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });
      const newerConfig = { ...testConfig, version: 10 };
      const existingItem = bwItem('item-id-1', 'rdc:rediacc', JSON.stringify(newerConfig));

      mockExecFile.mockImplementation(
        (
          _cmd: string,
          args: string[],
          _opts: unknown,
          cb: (err: null, res: { stdout: string }) => void
        ) => {
          if (args.includes('list')) {
            cb(null, { stdout: JSON.stringify([existingItem]) });
          } else {
            cb(null, { stdout: '' });
          }
        }
      );

      const result = await adapter.push(testConfig, 'rediacc');
      expect(result.success).toBe(false);
      expect(result.error).toContain('Version conflict');
    });

    it('stores config in the correct folder when bwFolderId is set', async () => {
      const adapter = new BitwardenStoreAdapter({
        name: 'test',
        type: 'bitwarden',
        bwFolderId: 'folder-123',
      });

      mockExecFile.mockImplementation(
        (
          _cmd: string,
          args: string[],
          _opts: unknown,
          cb: (err: null, res: { stdout: string }) => void
        ) => {
          if (args.includes('list')) {
            cb(null, { stdout: JSON.stringify([]) });
          } else if (args.includes('create')) {
            const encoded = args[args.indexOf('create') + 2];
            const decoded = JSON.parse(Buffer.from(encoded, 'base64').toString());
            expect(decoded.folderId).toBe('folder-123');
            cb(null, { stdout: '{}' });
          } else {
            cb(null, { stdout: '' });
          }
        }
      );

      const result = await adapter.push(testConfig, 'rediacc');
      expect(result.success).toBe(true);
    });
  });

  // ============================================================================
  // pull()
  // ============================================================================

  describe('pull()', () => {
    it('returns config when item exists', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });
      const item = bwItem('item-1', 'rdc:production', JSON.stringify(testConfig));

      mockExecFile.mockImplementation(
        (
          _cmd: string,
          args: string[],
          _opts: unknown,
          cb: (err: null, res: { stdout: string }) => void
        ) => {
          if (args.includes('list')) {
            cb(null, { stdout: JSON.stringify([item]) });
          } else {
            cb(null, { stdout: '' });
          }
        }
      );

      const result = await adapter.pull('production');
      expect(result.success).toBe(true);
      expect(result.config?.id).toBe('test-uuid-1234');
      expect(result.config?.version).toBe(3);
    });

    it('returns not-found error when item does not exist', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });

      mockExecFile.mockImplementation(mockBwResponse(JSON.stringify([])));

      const result = await adapter.pull('nonexistent');
      expect(result.success).toBe(false);
      expect(result.error).toContain('not found');
    });

    it('returns error when item notes contain invalid JSON', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });
      const item = bwItem('item-1', 'rdc:broken', 'not json');

      mockExecFile.mockImplementation(mockBwResponse(JSON.stringify([item])));

      const result = await adapter.pull('broken');
      expect(result.success).toBe(false);
      expect(result.error).toContain('invalid JSON');
    });
  });

  // ============================================================================
  // list()
  // ============================================================================

  describe('list()', () => {
    it('returns sorted config names from rdc: prefixed items', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });
      const items = [
        bwItem('1', 'rdc:staging', '{}'),
        bwItem('2', 'rdc:production', '{}'),
        bwItem('3', 'rdc:rediacc', '{}'),
        bwItem('4', 'unrelated-item', '{}'),
      ];

      mockExecFile.mockImplementation(mockBwResponse(JSON.stringify(items)));

      const result = await adapter.list();
      expect(result).toEqual(['production', 'rediacc', 'staging']);
    });

    it('filters by folder ID when set', async () => {
      const adapter = new BitwardenStoreAdapter({
        name: 'test',
        type: 'bitwarden',
        bwFolderId: 'folder-1',
      });
      const items = [
        bwItem('1', 'rdc:in-folder', '{}', 'folder-1'),
        bwItem('2', 'rdc:other-folder', '{}', 'folder-2'),
        bwItem('3', 'rdc:no-folder', '{}', null),
      ];

      mockExecFile.mockImplementation(mockBwResponse(JSON.stringify(items)));

      const result = await adapter.list();
      expect(result).toEqual(['in-folder']);
    });

    it('returns empty array when no configs exist', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });

      mockExecFile.mockImplementation(mockBwResponse(JSON.stringify([])));

      const result = await adapter.list();
      expect(result).toEqual([]);
    });
  });

  // ============================================================================
  // delete()
  // ============================================================================

  describe('delete()', () => {
    it('deletes existing item and returns success', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });
      const item = bwItem('item-to-delete', 'rdc:staging', '{}');

      mockExecFile.mockImplementation(
        (
          _cmd: string,
          args: string[],
          _opts: unknown,
          cb: (err: null, res: { stdout: string }) => void
        ) => {
          if (args.includes('list')) {
            cb(null, { stdout: JSON.stringify([item]) });
          } else if (args.includes('delete')) {
            expect(args).toContain('item-to-delete');
            cb(null, { stdout: '' });
          } else {
            cb(null, { stdout: '' });
          }
        }
      );

      const result = await adapter.delete('staging');
      expect(result.success).toBe(true);
    });

    it('returns not-found error for nonexistent config', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });

      mockExecFile.mockImplementation(mockBwResponse(JSON.stringify([])));

      const result = await adapter.delete('nonexistent');
      expect(result.success).toBe(false);
      expect(result.error).toContain('not found');
    });
  });

  // ============================================================================
  // verify()
  // ============================================================================

  describe('verify()', () => {
    it('returns true when vault is unlocked and accessible', async () => {
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });

      mockExecFile.mockImplementation(
        (
          _cmd: string,
          args: string[],
          _opts: unknown,
          cb: (err: null, res: { stdout: string }) => void
        ) => {
          if (args.includes('status')) {
            cb(null, { stdout: bwStatus('unlocked') });
          } else if (args.includes('list')) {
            cb(null, { stdout: JSON.stringify([]) });
          } else {
            cb(null, { stdout: '' });
          }
        }
      );

      // Remove BW_SESSION so verify checks status
      delete process.env.BW_SESSION;
      const result = await adapter.verify();
      expect(result).toBe(true);
    });

    it('returns false when vault is locked', async () => {
      delete process.env.BW_SESSION;
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });

      mockExecFile.mockImplementation(mockBwResponse(bwStatus('locked')));

      const result = await adapter.verify();
      expect(result).toBe(false);
    });

    it('returns false when bw CLI is not available', async () => {
      delete process.env.BW_SESSION;
      const adapter = new BitwardenStoreAdapter({ name: 'test', type: 'bitwarden' });

      mockExecFile.mockImplementation(mockBwError('spawn bw ENOENT'));

      const result = await adapter.verify();
      expect(result).toBe(false);
    });
  });
});
