import { EventEmitter } from 'node:events';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const spawn = vi.fn();
const success = vi.fn();
const error = vi.fn();
const setExitCode = vi.fn();
const handleError = vi.fn();

vi.mock('node:child_process', () => ({ spawn: (...args: unknown[]) => spawn(...args) }));
vi.mock('../../../services/executor/ops-executor.js', () => ({
  opsExecutorService: { getRenetPath: async () => 'C:\\rediacc\\renet.exe' },
}));
vi.mock('../../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: (m: string) => success(m),
    error: (m: string) => error(m),
  },
}));
vi.mock('../../../services/core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../services/core/request-context.js')>()),
  setExitCode: (c: number) => setExitCode(c),
}));
vi.mock('../../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/errors.js')>()),
  handleError: (e: unknown) => handleError(e),
}));

const { registerOpsSetupCommand } = await import('../setup.js');

const realPlatform = process.platform;
function setPlatform(value: NodeJS.Platform): void {
  Object.defineProperty(process, 'platform', { value, configurable: true });
}

/** A child that closes with `code` on the next tick. */
function childExiting(code: number | null): EventEmitter {
  const child = new EventEmitter();
  setImmediate(() => child.emit('close', code));
  return child;
}

async function runSetup(): Promise<void> {
  const root = new Command();
  root.exitOverride();
  registerOpsSetupCommand(root.command('ops'), root);
  await root.parseAsync(['node', 'rdc', 'ops', 'setup']);
}

describe('ops setup on Windows follows renet ops host setup', () => {
  beforeEach(() => {
    for (const fn of [spawn, success, error, setExitCode, handleError]) fn.mockReset();
    setPlatform('win32');
  });
  afterEach(() => setPlatform(realPlatform));

  it.each([1, 3, null])(
    'exit %s fails with the failure line and never the success line',
    async (code) => {
      spawn.mockReturnValue(childExiting(code));
      await runSetup();
      expect(spawn.mock.calls[0].slice(0, 2)).toEqual([
        'C:\\rediacc\\renet.exe',
        ['ops', 'host', 'setup'],
      ]);
      expect(success).not.toHaveBeenCalled();
      expect(error).toHaveBeenCalledWith('Installation failed');
      expect(setExitCode).toHaveBeenCalledWith(code ?? 1);
    }
  );

  it('exit 0 prints the success line and exits 0', async () => {
    spawn.mockReturnValue(childExiting(0));
    await runSetup();
    expect(success).toHaveBeenCalledWith('Prerequisites installed successfully');
    expect(error).not.toHaveBeenCalled();
    expect(setExitCode).toHaveBeenCalledWith(0);
  });
});
