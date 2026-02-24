import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SELF_HOSTED_MODES } from '../../config/command-registry.js';
import type { RdcConfig } from '../../types/index.js';

// Mock configService and outputService
const mockGetCurrent = vi.fn();
const mockError = vi.fn();

vi.mock('../../services/config-resources.js', () => ({
  configService: {
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
  const hooks = (cmd as unknown as { _lifeCycleHooks: Record<string, HookFn[] | undefined> })
    ._lifeCycleHooks;
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
      mockGetCurrent.mockResolvedValue({ id: '1', version: 1 } as RdcConfig);

      const cmd = new Command('auth');
      addModeGuard(cmd, ['cloud']);
      await runGuardHook(cmd);

      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('"auth"'));
      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('cloud'));
      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('local'));
      expect(exitSpy).toHaveBeenCalledWith(1);
    });

    it('should block local command in cloud mode', async () => {
      mockGetCurrent.mockResolvedValue({
        id: '1',
        version: 1,
        apiUrl: 'https://api.example.com',
        token: 'tok',
      } as RdcConfig);

      const cmd = new Command('repo');
      addModeGuard(cmd, SELF_HOSTED_MODES);
      await runGuardHook(cmd);

      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('"repo"'));
      expect(exitSpy).toHaveBeenCalledWith(1);
    });

    it('should allow cloud-only command in cloud mode', async () => {
      mockGetCurrent.mockResolvedValue({
        id: '1',
        version: 1,
        apiUrl: 'https://api.example.com',
        token: 'tok',
      } as RdcConfig);

      const cmd = new Command('auth');
      addModeGuard(cmd, ['cloud']);
      await runGuardHook(cmd);

      expect(mockError).not.toHaveBeenCalled();
      expect(exitSpy).not.toHaveBeenCalled();
    });

    it('should allow cloud-only command when apiUrl set but no token (pre-auth)', async () => {
      mockGetCurrent.mockResolvedValue({
        id: '1',
        version: 1,
        apiUrl: 'https://api.example.com',
      } as RdcConfig);

      const cmd = new Command('auth');
      addModeGuard(cmd, ['cloud']);
      await runGuardHook(cmd);

      expect(mockError).not.toHaveBeenCalled();
      expect(exitSpy).not.toHaveBeenCalled();
    });

    it('should allow local command in local mode', async () => {
      mockGetCurrent.mockResolvedValue({ id: '1', version: 1 } as RdcConfig);

      const cmd = new Command('repo');
      addModeGuard(cmd, SELF_HOSTED_MODES);
      await runGuardHook(cmd);

      expect(mockError).not.toHaveBeenCalled();
      expect(exitSpy).not.toHaveBeenCalled();
    });

    it('should not add guard for all-modes command', () => {
      const cmd = new Command('config');
      addModeGuard(cmd, ['cloud', 'local']);

      // No hooks should have been added
      const hooks = (cmd as unknown as { _lifeCycleHooks: Record<string, HookFn[] | undefined> })
        ._lifeCycleHooks;
      expect(hooks.preAction ?? []).toHaveLength(0);
    });

    it('should default to local when context is null', async () => {
      mockGetCurrent.mockResolvedValue(null);

      // cloud-only command should be blocked when no config (defaults to local)
      const cmd = new Command('auth');
      addModeGuard(cmd, ['cloud']);
      await runGuardHook(cmd);

      expect(mockError).toHaveBeenCalledWith(expect.stringContaining('"auth"'));
      expect(exitSpy).toHaveBeenCalledWith(1);
    });

    it('should allow self-hosted command when context is null (default local)', async () => {
      mockGetCurrent.mockResolvedValue(null);

      const cmd = new Command('repo');
      addModeGuard(cmd, SELF_HOSTED_MODES);
      await runGuardHook(cmd);

      expect(mockError).not.toHaveBeenCalled();
      expect(exitSpy).not.toHaveBeenCalled();
    });
  });
});
