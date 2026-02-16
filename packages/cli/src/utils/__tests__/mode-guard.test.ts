import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SELF_HOSTED_MODES } from '../../config/command-registry.js';
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
const { addModeGuard } = await import('../mode-guard.js');

type HookFn = (thisCommand: Command, actionCommand: Command) => Promise<void> | void;

async function runGuardHook(cmd: Command): Promise<void> {
  const hooks = (cmd as unknown as { _lifeCycleHooks: Record<string, HookFn[]> })._lifeCycleHooks;
  const preActionHooks = hooks.preAction;
  if (!preActionHooks) return;
  for (const hook of preActionHooks) {
    await hook(cmd, cmd);
  }
}

describe('utils/mode-guard', () => {
  let exitSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    exitSpy = vi.spyOn(process, 'exit').mockImplementation((() => {}) as never);
  });

  afterEach(() => {
    exitSpy.mockRestore();
  });

  describe('addModeGuard', () => {
    it('should block cloud-only command in local mode', async () => {
      mockGetCurrent.mockResolvedValue({ name: 'test', mode: 'local' } as NamedContext);

      const cmd = new Command('auth');
      addModeGuard(cmd, ['cloud']);
      await runGuardHook(cmd);

      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('"auth"'));
      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('cloud'));
      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('local'));
      expect(exitSpy).toHaveBeenCalledWith(1);
    });

    it('should block cloud-only command in s3 mode', async () => {
      mockGetCurrent.mockResolvedValue({ name: 'test', mode: 's3' } as NamedContext);

      const cmd = new Command('repository');
      addModeGuard(cmd, ['cloud']);
      await runGuardHook(cmd);

      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('"repository"'));
      expect(exitSpy).toHaveBeenCalledWith(1);
    });

    it('should block local|s3 command in cloud mode', async () => {
      mockGetCurrent.mockResolvedValue({ name: 'test', mode: 'cloud' } as NamedContext);

      const cmd = new Command('repo');
      addModeGuard(cmd, SELF_HOSTED_MODES);
      await runGuardHook(cmd);

      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('"repo"'));
      expect(exitSpy).toHaveBeenCalledWith(1);
    });

    it('should allow cloud-only command in cloud mode', async () => {
      mockGetCurrent.mockResolvedValue({ name: 'test', mode: 'cloud' } as NamedContext);

      const cmd = new Command('auth');
      addModeGuard(cmd, ['cloud']);
      await runGuardHook(cmd);

      expect(mockError).not.toHaveBeenCalled();
      expect(exitSpy).not.toHaveBeenCalled();
    });

    it('should allow local|s3 command in local mode', async () => {
      mockGetCurrent.mockResolvedValue({ name: 'test', mode: 'local' } as NamedContext);

      const cmd = new Command('repo');
      addModeGuard(cmd, SELF_HOSTED_MODES);
      await runGuardHook(cmd);

      expect(mockError).not.toHaveBeenCalled();
      expect(exitSpy).not.toHaveBeenCalled();
    });

    it('should not add guard for all-modes command', async () => {
      const cmd = new Command('context');
      addModeGuard(cmd, ['cloud', 'local', 's3']);

      // No hooks should have been added
      const hooks = (cmd as unknown as { _lifeCycleHooks: Record<string, HookFn[]> })
        ._lifeCycleHooks;
      expect(hooks.preAction ?? []).toHaveLength(0);
    });

    it('should default to cloud when context is null', async () => {
      mockGetCurrent.mockResolvedValue(null);

      const cmd = new Command('auth');
      addModeGuard(cmd, ['cloud']);
      await runGuardHook(cmd);

      expect(mockError).not.toHaveBeenCalled();
      expect(exitSpy).not.toHaveBeenCalled();
    });
  });
});
