import { createHash } from 'node:crypto';
import https from 'node:https';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  acquireUpdateLock,
  getPlatformKey,
  isSEA,
  isUpdateDisabled,
  releaseUpdateLock,
} from '../../utils/platform.js';
import {
  checkForUpdate,
  compareVersions,
  type ManifestAsset,
  performUpdate,
  type UpdateManifest,
} from '../updater.js';

vi.mock('../../utils/platform.js', () => ({
  isSEA: vi.fn(),
  isUpdateDisabled: vi.fn(),
  getPlatformKey: vi.fn(),
  getOldBinaryPath: vi.fn(),
  acquireUpdateLock: vi.fn(),
  releaseUpdateLock: vi.fn(),
  cleanupOldBinary: vi.fn(),
  LOCK_FILE: '/tmp/.rediacc/update.lock',
}));

vi.mock('node:https', () => ({
  default: {
    get: vi.fn(),
  },
}));

vi.mock('node:fs/promises', () => ({
  chmod: vi.fn().mockResolvedValue(undefined),
  rename: vi.fn().mockResolvedValue(undefined),
  writeFile: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('node:crypto', () => ({
  createHash: vi.fn(),
}));

type EventHandler = (...args: unknown[]) => void;

/** Create a mock HTTP response that emits data asynchronously */
function createMockResponse(statusCode: number, body: string) {
  const handlers = new Map<string, EventHandler[]>();
  const res = {
    statusCode,
    headers: {},
    on(event: string, handler: EventHandler) {
      const list = handlers.get(event) ?? [];
      list.push(handler);
      handlers.set(event, list);
      return res;
    },
    resume: vi.fn(),
  };
  setTimeout(() => {
    const dataHandlers = handlers.get('data');
    if (dataHandlers) {
      for (const h of dataHandlers) h(Buffer.from(body));
    }
    const endHandlers = handlers.get('end');
    if (endHandlers) {
      for (const h of endHandlers) h();
    }
  }, 0);
  return res;
}

function createMockBinaryResponse(statusCode: number, data: Buffer) {
  const handlers = new Map<string, EventHandler[]>();
  const res = {
    statusCode,
    headers: {},
    on(event: string, handler: EventHandler) {
      const list = handlers.get(event) ?? [];
      list.push(handler);
      handlers.set(event, list);
      return res;
    },
    resume: vi.fn(),
  };
  setTimeout(() => {
    const dataHandlers = handlers.get('data');
    if (dataHandlers) {
      for (const h of dataHandlers) h(data);
    }
    const endHandlers = handlers.get('end');
    if (endHandlers) {
      for (const h of endHandlers) h();
    }
  }, 0);
  return res;
}

function createMockRequest() {
  return { on: vi.fn().mockReturnThis(), destroy: vi.fn() };
}

function createErrorRequest() {
  const handlers = new Map<string, EventHandler[]>();
  const req = {
    on(event: string, handler: EventHandler) {
      const list = handlers.get(event) ?? [];
      list.push(handler);
      handlers.set(event, list);
      return req;
    },
    destroy: vi.fn(),
  };
  setTimeout(() => {
    const errorHandlers = handlers.get('error');
    if (errorHandlers) {
      for (const h of errorHandlers) h(new Error('ECONNREFUSED'));
    }
  }, 0);
  return req;
}

describe('services/updater', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('compareVersions()', () => {
    it('0.4.41 < 0.4.42 returns -1', () => {
      expect(compareVersions('0.4.41', '0.4.42')).toBe(-1);
    });

    it('0.4.42 == 0.4.42 returns 0', () => {
      expect(compareVersions('0.4.42', '0.4.42')).toBe(0);
    });

    it('0.4.43 > 0.4.42 returns 1', () => {
      expect(compareVersions('0.4.43', '0.4.42')).toBe(1);
    });

    it('1.0.0 > 0.99.99 returns 1', () => {
      expect(compareVersions('1.0.0', '0.99.99')).toBe(1);
    });

    it('strips v prefix before comparing', () => {
      expect(compareVersions('v0.4.42', '0.4.42')).toBe(0);
    });

    it('missing patch treated as 0', () => {
      expect(compareVersions('0.4', '0.4.1')).toBe(-1);
    });

    it('1.0.0 > 0.0.1 returns 1', () => {
      expect(compareVersions('1.0.0', '0.0.1')).toBe(1);
    });
  });

  describe('checkForUpdate()', () => {
    beforeEach(() => {
      vi.mocked(isSEA).mockReturnValue(true);
      vi.mocked(isUpdateDisabled).mockReturnValue(false);
    });

    it('returns not available when not SEA', async () => {
      vi.mocked(isSEA).mockReturnValue(false);

      const result = await checkForUpdate('0.4.42');

      expect(result.updateAvailable).toBe(false);
      expect(result.currentVersion).toBe('0.4.42');
    });

    it('returns not available when disabled', async () => {
      vi.mocked(isUpdateDisabled).mockReturnValue(true);

      const result = await checkForUpdate('0.4.42');

      expect(result.updateAvailable).toBe(false);
    });

    it('returns available when manifest has newer version', async () => {
      const manifest: UpdateManifest = {
        version: '0.5.0',
        assets: {
          'linux-x64': { url: 'https://example.com/rdc', sha256: 'abc123' },
        },
      };

      vi.mocked(https.get).mockImplementation((_url, callback) => {
        const res = createMockResponse(200, JSON.stringify(manifest));
        (callback as (res: unknown) => void)(res);
        return createMockRequest() as unknown as ReturnType<typeof https.get>;
      });

      const result = await checkForUpdate('0.4.42');

      expect(result.updateAvailable).toBe(true);
      expect(result.latestVersion).toBe('0.5.0');
    });

    it('returns not available when manifest has same version', async () => {
      const manifest: UpdateManifest = {
        version: '0.4.42',
        assets: {},
      };

      vi.mocked(https.get).mockImplementation((_url, callback) => {
        const res = createMockResponse(200, JSON.stringify(manifest));
        (callback as (res: unknown) => void)(res);
        return createMockRequest() as unknown as ReturnType<typeof https.get>;
      });

      const result = await checkForUpdate('0.4.42');

      expect(result.updateAvailable).toBe(false);
    });

    it('returns not available on network error', async () => {
      vi.mocked(https.get).mockImplementation((_url, _callback) => {
        return createErrorRequest() as unknown as ReturnType<typeof https.get>;
      });

      const result = await checkForUpdate('0.4.42');

      expect(result.updateAvailable).toBe(false);
    });
  });

  describe('performUpdate()', () => {
    beforeEach(() => {
      vi.mocked(isSEA).mockReturnValue(true);
      vi.mocked(getPlatformKey).mockReturnValue('linux-x64');
      vi.mocked(acquireUpdateLock).mockResolvedValue(true);
      vi.mocked(releaseUpdateLock).mockResolvedValue(undefined);
      Object.defineProperty(process, 'execPath', { value: '/usr/local/bin/rdc', writable: true });
      Object.defineProperty(process, 'platform', { value: 'linux' });
    });

    it('returns notSEA error when not SEA binary', async () => {
      vi.mocked(isSEA).mockReturnValue(false);

      const result = await performUpdate('0.4.42');

      expect(result.success).toBe(false);
      expect(result.error).toBe('notSEA');
    });

    it('returns unsupportedPlatform error when platform is null', async () => {
      vi.mocked(getPlatformKey).mockReturnValue(null);

      const result = await performUpdate('0.4.42');

      expect(result.success).toBe(false);
      expect(result.error).toBe('unsupportedPlatform');
    });

    it('returns lockFailed error when lock cannot be acquired', async () => {
      vi.mocked(acquireUpdateLock).mockResolvedValue(false);

      const result = await performUpdate('0.4.42');

      expect(result.success).toBe(false);
      expect(result.error).toBe('lockFailed');
    });

    it('returns alreadyUpToDate when same version without force', async () => {
      const manifest: UpdateManifest = {
        version: '0.4.42',
        assets: {
          'linux-x64': { url: 'https://example.com/rdc', sha256: 'abc123' },
        },
      };

      vi.mocked(https.get).mockImplementation((_url, callback) => {
        const res = createMockResponse(200, JSON.stringify(manifest));
        (callback as (res: unknown) => void)(res);
        return createMockRequest() as unknown as ReturnType<typeof https.get>;
      });

      const result = await performUpdate('0.4.42');

      expect(result.success).toBe(true);
      expect(result.error).toBe('alreadyUpToDate');
    });

    it('returns checksumMismatch when SHA256 does not match', async () => {
      const binaryContent = Buffer.from('fake-binary-content');
      const wrongSha = 'wrong_sha256_value';

      const manifest: UpdateManifest = {
        version: '0.5.0',
        assets: {
          'linux-x64': {
            url: 'https://example.com/rdc-linux-x64',
            sha256: wrongSha,
          } satisfies ManifestAsset,
        },
      };

      let callCount = 0;
      vi.mocked(https.get).mockImplementation((_url, callback) => {
        callCount++;
        if (callCount === 1) {
          const res = createMockResponse(200, JSON.stringify(manifest));
          (callback as (res: unknown) => void)(res);
        } else {
          const res = createMockBinaryResponse(200, binaryContent);
          (callback as (res: unknown) => void)(res);
        }
        return createMockRequest() as unknown as ReturnType<typeof https.get>;
      });

      const mockDigest = vi.fn().mockReturnValue('actual_sha256_hash');
      const mockUpdate = vi.fn().mockReturnValue({ digest: mockDigest });
      vi.mocked(createHash).mockReturnValue({ update: mockUpdate } as unknown as ReturnType<
        typeof createHash
      >);

      const result = await performUpdate('0.4.42', { force: true });

      expect(result.success).toBe(false);
      expect(result.error).toBe('checksumMismatch');
    });
  });
});
