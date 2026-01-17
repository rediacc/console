import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Create mock function that will be used by promisify
const execAsyncMock = vi.fn();

// Mock util.promisify to return our mock exec
vi.mock('node:util', () => ({
  promisify: () => execAsyncMock,
}));

// Import the module under test
const { RenetResolver, getRenetResolver } = await import('../RenetResolver');

describe('RenetResolver', () => {
  let originalEnv: NodeJS.ProcessEnv;

  beforeEach(() => {
    // Save original env
    originalEnv = { ...process.env };

    // Clear env vars that affect resolution
    delete process.env.RENET_BINARY_PATH;
    delete process.env.RENET_ROOT;

    // Reset mocks
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Restore original env
    process.env = originalEnv;
  });

  describe('ensureBinary with env vars', () => {
    it('should use RENET_BINARY_PATH env var when set and binary works', async () => {
      process.env.RENET_BINARY_PATH = '/custom/path/renet';

      // Mock successful version check
      execAsyncMock.mockResolvedValue({ stdout: 'renet v1.0.0', stderr: '' });

      const resolver = new RenetResolver();
      const result = await resolver.ensureBinary();

      expect(result.source).toBe('env');
      expect(result.path).toBe('/custom/path/renet');
      expect(result.builtNow).toBe(false);
      expect(execAsyncMock).toHaveBeenCalledWith('/custom/path/renet version', { timeout: 5000 });
    });

    it('should throw error when env path binary is invalid', async () => {
      process.env.RENET_BINARY_PATH = '/invalid/path/renet';

      execAsyncMock.mockRejectedValue(new Error('Command not found'));

      const resolver = new RenetResolver();
      await expect(resolver.ensureBinary()).rejects.toThrow('not working');
    });
  });

  describe('getPath', () => {
    it('should throw when ensureBinary not called', () => {
      const resolver = new RenetResolver();
      expect(() => resolver.getPath()).toThrow('Call ensureBinary() first');
    });

    it('should return cached path after ensureBinary succeeds', async () => {
      process.env.RENET_BINARY_PATH = '/custom/renet';

      execAsyncMock.mockResolvedValue({ stdout: 'v1.0.0', stderr: '' });

      const resolver = new RenetResolver();
      await resolver.ensureBinary();

      expect(resolver.getPath()).toBe('/custom/renet');
      // Call again to verify caching
      expect(resolver.getPath()).toBe('/custom/renet');
    });
  });

  describe('getMonorepoRoot', () => {
    it('should return an absolute path', () => {
      const resolver = new RenetResolver();
      const root = resolver.getMonorepoRoot();

      expect(path.isAbsolute(root)).toBe(true);
    });

    it('should return consistent path across calls', () => {
      const resolver = new RenetResolver();
      const root1 = resolver.getMonorepoRoot();
      const root2 = resolver.getMonorepoRoot();

      expect(root1).toBe(root2);
    });
  });

  describe('getRenetResolver singleton', () => {
    it('should return the same instance on multiple calls', () => {
      const resolver1 = getRenetResolver();
      const resolver2 = getRenetResolver();

      expect(resolver1).toBe(resolver2);
    });

    it('should be a RenetResolver instance', () => {
      const resolver = getRenetResolver();
      expect(resolver).toBeInstanceOf(RenetResolver);
    });
  });

  describe('RenetResolution interface', () => {
    it('should return correct resolution object structure for env source', async () => {
      process.env.RENET_BINARY_PATH = '/test/renet';
      execAsyncMock.mockResolvedValue({ stdout: 'v1.0.0', stderr: '' });

      const resolver = new RenetResolver();
      const result = await resolver.ensureBinary();

      // Verify structure matches RenetResolution interface
      expect(result).toHaveProperty('path');
      expect(result).toHaveProperty('source');
      expect(result).toHaveProperty('builtNow');
      expect(typeof result.path).toBe('string');
      expect(['env', 'source-build', 'path']).toContain(result.source);
      expect(typeof result.builtNow).toBe('boolean');
    });
  });
});

// Test getRenetBinaryPath fallback behavior (imported from renetPath.ts)
describe('getRenetBinaryPath fallback', () => {
  let originalEnv: NodeJS.ProcessEnv;

  beforeEach(() => {
    originalEnv = { ...process.env };
    delete process.env.RENET_BINARY_PATH;
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('should use RENET_BINARY_PATH env var when resolver not initialized', async () => {
    process.env.RENET_BINARY_PATH = '/ci/path/renet';

    // Import fresh to avoid cached resolver
    const { getRenetBinaryPath } = await import('../renetPath');

    // Create new resolver instance that hasn't been initialized
    // The getRenetBinaryPath should fall back to env var
    const result = getRenetBinaryPath();

    // Should either return the env var path or the cached resolver path
    // In CI mode with no resolver init, it should return the env var path
    expect(result).toBe('/ci/path/renet');
  });
});
