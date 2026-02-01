import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NamedContext } from '../../types/index.js';

// Mock contextService and outputService
const mockGetCurrent = vi.fn();
const mockError = vi.fn();

vi.mock('../../services/context.js', () => ({
  contextService: {
    getCurrent: (...args: unknown[]) => mockGetCurrent(...args),
  },
}));

vi.mock('../../services/output.js', () => ({
  outputService: {
    error: (...args: unknown[]) => mockError(...args),
  },
}));

// Must import AFTER vi.mock calls
const { addCloudOnlyGuard, markCloudOnly } = await import('../cloud-guard.js');

describe('utils/cloud-guard', () => {
  let exitSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    exitSpy = vi.spyOn(process, 'exit').mockImplementation((() => {}) as never);
  });

  afterEach(() => {
    exitSpy.mockRestore();
  });

  describe('addCloudOnlyGuard', () => {
    async function runGuardHook(cmd: Command): Promise<void> {
      // Commander stores hooks internally; trigger via parseAsync with a dummy action
      // Instead, we directly test the guard by simulating what commander does:
      // The preAction hook is called before the action runs.
      // We can access it via the internal _lifeCycleHooks map.
      const hooks = (cmd as unknown as { _lifeCycleHooks: Record<string, Function[]> })
        ._lifeCycleHooks;
      const preActionHooks = hooks?.preAction ?? [];
      for (const hook of preActionHooks) {
        await hook(cmd, cmd);
      }
    }

    it('should block execution in local mode', async () => {
      mockGetCurrent.mockResolvedValue({ name: 'test', mode: 'local' } as NamedContext);

      const cmd = new Command('test-cmd');
      addCloudOnlyGuard(cmd);

      await runGuardHook(cmd);

      expect(mockError).toHaveBeenCalledWith(
        expect.stringContaining('"test-cmd" is only available in cloud mode')
      );
      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('local'));
      expect(exitSpy).toHaveBeenCalledWith(1);
    });

    it('should block execution in s3 mode', async () => {
      mockGetCurrent.mockResolvedValue({ name: 'test', mode: 's3' } as NamedContext);

      const cmd = new Command('my-command');
      addCloudOnlyGuard(cmd);

      await runGuardHook(cmd);

      expect(mockError).toHaveBeenCalledWith(
        expect.stringContaining('"my-command" is only available in cloud mode')
      );
      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('s3'));
      expect(exitSpy).toHaveBeenCalledWith(1);
    });

    it('should allow execution in cloud mode', async () => {
      mockGetCurrent.mockResolvedValue({ name: 'test', mode: 'cloud' } as NamedContext);

      const cmd = new Command('test-cmd');
      addCloudOnlyGuard(cmd);

      await runGuardHook(cmd);

      expect(mockError).not.toHaveBeenCalled();
      expect(exitSpy).not.toHaveBeenCalled();
    });

    it('should default to cloud when context is null', async () => {
      mockGetCurrent.mockResolvedValue(null);

      const cmd = new Command('test-cmd');
      addCloudOnlyGuard(cmd);

      await runGuardHook(cmd);

      expect(mockError).not.toHaveBeenCalled();
      expect(exitSpy).not.toHaveBeenCalled();
    });

    it('should include command name and current mode in error message', async () => {
      mockGetCurrent.mockResolvedValue({ name: 'test', mode: 'local' } as NamedContext);

      const cmd = new Command('repository');
      addCloudOnlyGuard(cmd);

      await runGuardHook(cmd);

      expect(mockError).toHaveBeenCalledWith(
        '"repository" is only available in cloud mode. Current mode: local'
      );
    });
  });

  describe('markCloudOnly', () => {
    it('should append [cloud only] to existing description', () => {
      const cmd = new Command('test-cmd').description('Manage resources');
      markCloudOnly(cmd);
      expect(cmd.description()).toBe('Manage resources [cloud only]');
    });

    it('should not double-append if already present', () => {
      const cmd = new Command('test-cmd').description('Manage resources [cloud only]');
      markCloudOnly(cmd);
      expect(cmd.description()).toBe('Manage resources [cloud only]');
    });

    it('should not modify empty description', () => {
      const cmd = new Command('test-cmd');
      markCloudOnly(cmd);
      expect(cmd.description()).toBe('');
    });
  });
});
