import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { acquireUpdateLock, getPlatformKey, isSEA, isUpdateDisabled } from '../../utils/platform.js';
// Note: startupUpdateCheck was removed — replaced by background-updater
import { checkForUpdate, compareVersions, performUpdate } from '../updater.js';

const mockReleaseLock = vi.fn().mockResolvedValue(undefined);

vi.mock('../../utils/platform.js', () => ({
  isSEA: vi.fn(),
  isUpdateDisabled: vi.fn(),
  getPlatformKey: vi.fn(),
  getOldBinaryPath: vi.fn().mockReturnValue('/usr/local/bin/rdc.old'),
  acquireUpdateLock: vi.fn(),
  STAGED_UPDATE_DIR: '/home/testuser/.cache/rediacc/staged-update',
}));

vi.mock('../update-state.js', () => ({
  getStagedBinaryPath: vi.fn().mockReturnValue('/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0'),
  readUpdateState: vi.fn().mockResolvedValue({
    schemaVersion: 1,
    lastCheckAt: null,
    lastAttemptAt: null,
    pendingUpdate: null,
    consecutiveFailures: 0,
    lastError: null,
  }),
  writeUpdateState: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../version.js', () => ({
  VERSION: '0.4.42',
}));

const mockFs = vi.hoisted(() => ({
  open: vi.fn(),
  readFile: vi.fn(),
  unlink: vi.fn().mockResolvedValue(undefined),
  rename: vi.fn().mockResolvedValue(undefined),
  chmod: vi.fn().mockResolvedValue(undefined),
  mkdir: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('node:fs', () => ({
  promises: mockFs,
}));

const mockHttpsGet = vi.hoisted(() => vi.fn());
vi.mock('node:https', () => ({
  get: mockHttpsGet,
}));

const mockHttpGet = vi.hoisted(() => vi.fn());
vi.mock('node:http', () => ({
  get: mockHttpGet,
}));

vi.mock('node:crypto', () => ({
  createHash: vi.fn(),
}));

const mockTelemetry = vi.hoisted(() => ({
  telemetryService: {
    trackEvent: vi.fn(),
  },
}));

vi.mock('../telemetry.js', () => mockTelemetry);

type EventHandler = (...args: unknown[]) => void;

/** Create a mock HTTP response that emits data/end events asynchronously */
function createMockResponse(
  statusCode: number,
  body: string | Buffer,
  headers: Record<string, string> = {}
) {
  const handlers = new Map<string, EventHandler[]>();
  const res = {
    statusCode,
    headers,
    on(event: string, handler: EventHandler) {
      const list = handlers.get(event) ?? [];
      list.push(handler);
      handlers.set(event, list);
      return res;
    },
    async *[Symbol.asyncIterator]() {
      const chunk = typeof body === 'string' ? Buffer.from(body) : body;
      yield await Promise.resolve(chunk);
    },
  };
  setTimeout(() => {
    const chunk = typeof body === 'string' ? Buffer.from(body) : body;
    const dataHandlers = handlers.get('data');
    if (dataHandlers) {
      for (const h of dataHandlers) h(chunk);
    }
    const endHandlers = handlers.get('end');
    if (endHandlers) {
      for (const h of endHandlers) h();
    }
  }, 0);
  return res;
}

function createMockRequest() {
  return {
    on: vi.fn().mockReturnThis(),
    destroy: vi.fn(),
    setTimeout: vi.fn(),
  };
}

function createErrorRequest(errorMessage = 'ECONNREFUSED') {
  const handlers = new Map<string, EventHandler[]>();
  const req = {
    on(event: string, handler: EventHandler) {
      const list = handlers.get(event) ?? [];
      list.push(handler);
      handlers.set(event, list);
      return req;
    },
    destroy: vi.fn(),
    setTimeout: vi.fn(),
  };
  setTimeout(() => {
    const errorHandlers = handlers.get('error');
    if (errorHandlers) {
      for (const h of errorHandlers) h(new Error(errorMessage));
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

      const result = await checkForUpdate();

      expect(result.updateAvailable).toBe(false);
      expect(result.currentVersion).toBe('0.4.42');
    });

    it('returns not available when disabled', async () => {
      vi.mocked(isUpdateDisabled).mockReturnValue(true);

      const result = await checkForUpdate();

      expect(result.updateAvailable).toBe(false);
    });

    it('returns available when manifest has newer version', async () => {
      const manifest = {
        version: '0.5.0',
        releaseDate: '2026-01-01T00:00:00Z',
        releaseNotesUrl: 'https://github.com/rediacc/console/releases/tag/v0.5.0',
        binaries: {
          'linux-x64': { url: 'https://example.com/rdc-linux-x64', sha256: 'abc123' },
        },
      };

      mockHttpsGet.mockImplementation(
        (_url: string, _opts: unknown, callback: (res: unknown) => void) => {
          const res = createMockResponse(200, JSON.stringify(manifest));
          callback(res);
          return createMockRequest();
        }
      );

      const result = await checkForUpdate();

      expect(result.updateAvailable).toBe(true);
      expect(result.latestVersion).toBe('0.5.0');
      expect(result.releaseNotesUrl).toBe('https://github.com/rediacc/console/releases/tag/v0.5.0');
    });

    it('returns not available when manifest has same version', async () => {
      const manifest = {
        version: '0.4.42',
        releaseDate: '2026-01-01T00:00:00Z',
        releaseNotesUrl: '',
        binaries: {},
      };

      mockHttpsGet.mockImplementation(
        (_url: string, _opts: unknown, callback: (res: unknown) => void) => {
          const res = createMockResponse(200, JSON.stringify(manifest));
          callback(res);
          return createMockRequest();
        }
      );

      const result = await checkForUpdate();

      expect(result.updateAvailable).toBe(false);
    });

    it('returns not available on network error', async () => {
      mockHttpsGet.mockImplementation((_url: string, _opts: unknown, _callback: unknown) => {
        return createErrorRequest();
      });

      const result = await checkForUpdate();

      expect(result.updateAvailable).toBe(false);
    });
  });

  describe('performUpdate()', () => {
    beforeEach(() => {
      vi.mocked(isSEA).mockReturnValue(true);
      vi.mocked(getPlatformKey).mockReturnValue('linux-x64');
      mockReleaseLock.mockClear();
      vi.mocked(acquireUpdateLock).mockResolvedValue(mockReleaseLock);
      Object.defineProperty(process, 'execPath', { value: '/usr/local/bin/rdc', writable: true });
      Object.defineProperty(process, 'platform', { value: 'linux' });
    });

    it('returns error when not SEA binary', async () => {
      vi.mocked(isSEA).mockReturnValue(false);

      const result = await performUpdate();

      expect(result.success).toBe(false);
      expect(result.error).toBe('update.errors.notSEA');
    });

    it('returns error when platform is unsupported', async () => {
      vi.mocked(getPlatformKey).mockReturnValue(null);

      const result = await performUpdate();

      expect(result.success).toBe(false);
      expect(result.error).toBe('update.errors.unsupportedPlatform');
    });

    it('returns error when lock cannot be acquired', async () => {
      vi.mocked(acquireUpdateLock).mockResolvedValue(null);

      const result = await performUpdate();

      expect(result.success).toBe(false);
      expect(result.error).toBe('update.errors.lockFailed');
    });

    it('releases lock after completion', async () => {
      const manifest = {
        version: '0.4.42',
        releaseDate: '2026-01-01T00:00:00Z',
        releaseNotesUrl: '',
        binaries: {},
      };

      mockHttpsGet.mockImplementation(
        (_url: string, _opts: unknown, callback: (res: unknown) => void) => {
          const res = createMockResponse(200, JSON.stringify(manifest));
          callback(res);
          return createMockRequest();
        }
      );

      await performUpdate();

      expect(mockReleaseLock).toHaveBeenCalled();
    });

    it('returns alreadyUpToDate when same version without force', async () => {
      const manifest = {
        version: '0.4.42',
        releaseDate: '2026-01-01T00:00:00Z',
        releaseNotesUrl: '',
        binaries: {
          'linux-x64': { url: 'https://example.com/rdc', sha256: 'abc123' },
        },
      };

      mockHttpsGet.mockImplementation(
        (_url: string, _opts: unknown, callback: (res: unknown) => void) => {
          const res = createMockResponse(200, JSON.stringify(manifest));
          callback(res);
          return createMockRequest();
        }
      );

      const result = await performUpdate();

      expect(result.success).toBe(true);
      expect(result.fromVersion).toBe('0.4.42');
      expect(result.toVersion).toBe('0.4.42');
    });

    it('returns noBinary when platform has no binary in manifest', async () => {
      const manifest = {
        version: '0.5.0',
        releaseDate: '2026-01-01T00:00:00Z',
        releaseNotesUrl: '',
        binaries: {
          'win-x64': { url: 'https://example.com/rdc.exe', sha256: 'abc' },
        },
      };

      mockHttpsGet.mockImplementation(
        (_url: string, _opts: unknown, callback: (res: unknown) => void) => {
          const res = createMockResponse(200, JSON.stringify(manifest));
          callback(res);
          return createMockRequest();
        }
      );

      const result = await performUpdate({ force: true });

      expect(result.success).toBe(false);
      expect(result.error).toBe('update.errors.noBinary');
      expect(result.toVersion).toBe('0.5.0');
    });

    it('returns checksumMismatch when SHA256 does not match', async () => {
      const binaryContent = Buffer.from('fake-binary-content');

      const manifest = {
        version: '0.5.0',
        releaseDate: '2026-01-01T00:00:00Z',
        releaseNotesUrl: '',
        binaries: {
          'linux-x64': { url: 'https://example.com/rdc-linux-x64', sha256: 'wrong_hash' },
        },
      };

      let callCount = 0;
      mockHttpsGet.mockImplementation(
        (_url: string, _opts: unknown, callback: (res: unknown) => void) => {
          callCount++;
          if (callCount === 1) {
            callback(createMockResponse(200, JSON.stringify(manifest)));
          } else {
            callback(
              createMockResponse(200, binaryContent, {
                'content-length': String(binaryContent.length),
              })
            );
          }
          return createMockRequest();
        }
      );

      // Mock file handle for download
      const mockFileHandle = {
        write: vi.fn().mockResolvedValue(undefined),
        close: vi.fn().mockResolvedValue(undefined),
      };
      mockFs.open.mockResolvedValue(mockFileHandle);
      mockFs.readFile.mockResolvedValue(binaryContent);

      const { createHash } = await import('node:crypto');
      const mockHashObj = {
        update: vi.fn(),
        digest: vi.fn().mockReturnValue('actual_different_hash'),
      };
      mockHashObj.update.mockReturnValue(mockHashObj);
      vi.mocked(createHash).mockReturnValue(
        mockHashObj as unknown as ReturnType<typeof createHash>
      );

      const result = await performUpdate({ force: true });

      expect(result.success).toBe(false);
      expect(result.error).toBe('update.errors.checksumMismatch');
    });

    it('stages binary on EBUSY instead of failing', async () => {
      const binaryContent = Buffer.from('fake-binary-content');

      const manifest = {
        version: '0.5.0',
        releaseDate: '2026-01-01T00:00:00Z',
        releaseNotesUrl: 'https://example.com/releases/v0.5.0',
        binaries: {
          'linux-x64': { url: 'https://example.com/rdc-linux-x64', sha256: 'correct_hash' },
        },
      };

      let callCount = 0;
      mockHttpsGet.mockImplementation(
        (_url: string, _opts: unknown, callback: (res: unknown) => void) => {
          callCount++;
          if (callCount === 1) {
            callback(createMockResponse(200, JSON.stringify(manifest)));
          } else {
            callback(
              createMockResponse(200, binaryContent, {
                'content-length': String(binaryContent.length),
              })
            );
          }
          return createMockRequest();
        }
      );

      // Mock file handle for download
      const mockFileHandle = {
        write: vi.fn().mockResolvedValue(undefined),
        close: vi.fn().mockResolvedValue(undefined),
      };
      mockFs.open.mockResolvedValue(mockFileHandle);
      mockFs.readFile.mockResolvedValue(binaryContent);

      // Hash matches
      const { createHash } = await import('node:crypto');
      const mockHashObj = {
        update: vi.fn(),
        digest: vi.fn().mockReturnValue('correct_hash'),
      };
      mockHashObj.update.mockReturnValue(mockHashObj);
      vi.mocked(createHash).mockReturnValue(
        mockHashObj as unknown as ReturnType<typeof createHash>
      );

      // Make first rename fail with EBUSY (binary is locked), rest succeed (staging)
      const ebusyError = new Error('EBUSY') as NodeJS.ErrnoException;
      ebusyError.code = 'EBUSY';
      mockFs.rename.mockRejectedValueOnce(ebusyError).mockResolvedValue(undefined);

      const result = await performUpdate({ force: true });

      // Should succeed with staging fallback
      expect(result.success).toBe(true);
      expect(result.toVersion).toBe('0.5.0');
      expect(result.error).toBe('update.errors.binaryBusy');

      // Should track telemetry event for staging
      expect(mockTelemetry.telemetryService.trackEvent).toHaveBeenCalledWith(
        'update.manual.staged',
        { version: '0.5.0' }
      );
    });
  });
});
