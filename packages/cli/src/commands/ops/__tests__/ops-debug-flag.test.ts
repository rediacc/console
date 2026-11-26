import { EventEmitter } from 'node:events';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const spawn = vi.fn();

vi.mock('node:child_process', () => ({ spawn: (...args: unknown[]) => spawn(...args) }));
vi.mock('../../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), error: vi.fn() },
}));

const { registerOpsUpCommand } = await import('../up.js');
const { registerOpsDownCommand } = await import('../down.js');
const { registerOpsSetupCommand } = await import('../setup.js');
const { opsExecutorService } = await import('../../../services/executor/ops-executor.js');

type Child = EventEmitter & { stdout: EventEmitter; stderr: EventEmitter };

function child(): Child {
  const c = new EventEmitter() as Child;
  c.stdout = new EventEmitter();
  c.stderr = new EventEmitter();
  setImmediate(() => c.emit('close', 0));
  return c;
}

async function run(args: string[]): Promise<void> {
  const root = new Command();
  root.exitOverride();
  const ops = root.command('ops');
  registerOpsUpCommand(ops, root);
  registerOpsDownCommand(ops, root);
  registerOpsSetupCommand(ops, root);
  await root.parseAsync(['node', 'rdc', 'ops', ...args]);
}

describe('rdc ops --debug is consumed by rdc, never forwarded to renet', () => {
  const realPlatform = process.platform;
  beforeEach(() => {
    spawn.mockReset();
    spawn.mockImplementation(() => child());
    vi.spyOn(opsExecutorService, 'getRenetPath').mockResolvedValue('renet');
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(process, 'platform', { value: realPlatform, configurable: true });
  });

  it.each([['up'], ['down']])(
    'ops %s --debug leaves --debug out of the renet argv',
    async (sub) => {
      await run([sub, '--debug']);
      const [, argv, opts] = spawn.mock.calls[0] as [
        string,
        string[],
        { env: Record<string, string> },
      ];
      expect(argv).toEqual(['ops', sub]);
      expect(opts.env.REDIACC_DEBUG).toBe('1');
    }
  );

  it('ops up keeps the flags renet accepts', async () => {
    await run(['up', '--basic', '--debug']);
    expect((spawn.mock.calls[0] as [string, string[]])[1]).toEqual(['ops', 'up', '--basic']);
  });

  it('ops setup --debug leaves --debug out of the renet argv', async () => {
    Object.defineProperty(process, 'platform', { value: 'win32', configurable: true });
    await run(['setup', '--debug']);
    const [, argv, opts] = spawn.mock.calls[0] as [
      string,
      string[],
      { env: Record<string, string> },
    ];
    expect(argv).toEqual(['ops', 'host', 'setup']);
    expect(opts.env.REDIACC_DEBUG).toBe('1');
  });

  it('ops setup --debug under sudo carries REDIACC_DEBUG through env', async () => {
    Object.defineProperty(process, 'platform', { value: 'linux', configurable: true });
    await run(['setup', '--debug']);
    const [cmd, argv] = spawn.mock.calls[0] as [string, string[]];
    expect(cmd).toBe('sudo');
    expect(argv).toEqual(['env', 'REDIACC_DEBUG=1', 'renet', 'ops', 'host', 'setup']);
  });

  it('ops setup without --debug sets no REDIACC_DEBUG', async () => {
    Object.defineProperty(process, 'platform', { value: 'win32', configurable: true });
    await run(['setup']);
    const opts = spawn.mock.calls[0]?.[2] as { env?: Record<string, string> };
    expect(opts.env?.REDIACC_DEBUG).toBeUndefined();
  });
});
