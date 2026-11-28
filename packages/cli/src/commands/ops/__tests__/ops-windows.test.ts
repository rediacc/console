import { EventEmitter } from 'node:events';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const spawn = vi.fn();
const info = vi.fn();

vi.mock('node:child_process', () => ({ spawn: (...args: unknown[]) => spawn(...args) }));
vi.mock('../../../services/core/output.js', () => ({
  outputService: { info: (...a: unknown[]) => info(...a), success: vi.fn(), error: vi.fn() },
}));

const { registerOpsUpCommand } = await import('../up.js');
const { registerOpsDownCommand } = await import('../down.js');
const { opsExecutorService } = await import('../../../services/executor/ops-executor.js');

type Child = EventEmitter & { stdout: EventEmitter; stderr: EventEmitter };

function child(stdout = ''): Child {
  const c = new EventEmitter() as Child;
  c.stdout = new EventEmitter();
  c.stderr = new EventEmitter();
  setImmediate(() => {
    if (stdout) c.stdout.emit('data', Buffer.from(stdout));
    c.emit('close', 0);
  });
  return c;
}

async function run(args: string[]): Promise<void> {
  const root = new Command();
  root.exitOverride();
  const ops = root.command('ops');
  registerOpsUpCommand(ops, root);
  registerOpsDownCommand(ops, root);
  await root.parseAsync(['node', 'rdc', 'ops', ...args]);
}

describe('rdc ops --windows and Windows clients in ops down', () => {
  beforeEach(() => {
    spawn.mockReset();
    info.mockReset();
    delete process.env.VM_WINDOWS;
    vi.spyOn(opsExecutorService, 'getRenetPath').mockResolvedValue('renet');
    vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    delete process.env.VM_WINDOWS;
  });

  it('ops up --windows hands VM_WINDOWS to renet and leaves it out of argv', async () => {
    let seen: string | undefined;
    spawn.mockImplementation(
      (_cmd: string, _argv: string[], opts: { env: Record<string, string> }) => {
        seen = opts.env.VM_WINDOWS;
        return child();
      }
    );
    await run(['up', '--basic', '--windows', '31, 32']);
    expect(seen).toBe('31,32');
    expect((spawn.mock.calls[0] as [string, string[]])[1]).toEqual(['ops', 'up', '--basic']);
    expect(process.env.VM_WINDOWS).toBeUndefined();
  });

  it('ops up without --windows sets no VM_WINDOWS', async () => {
    spawn.mockImplementation(() => child());
    await run(['up']);
    const opts = spawn.mock.calls[0]?.[2] as { env: Record<string, string> };
    expect(opts.env.VM_WINDOWS).toBeUndefined();
  });

  it('ops up --windows rejects a non-numeric list before spawning renet', async () => {
    spawn.mockImplementation(() => child());
    const exit = vi.spyOn(process, 'exit').mockImplementation((() => undefined) as never);
    await run(['up', '--windows', '31,abc']);
    expect(spawn).not.toHaveBeenCalled();
    expect(exit).toHaveBeenCalled();
  });

  it('ops down names the Windows clients that status reports', async () => {
    const status = JSON.stringify({
      vms: [
        { id: 1, name: 'rediacc1', ip: '192.168.111.1', status: 'running', role: 'bridge' },
        {
          id: 31,
          name: 'rediacc31',
          ip: '192.168.111.31',
          status: 'running',
          role: 'windows-client',
        },
      ],
    });
    spawn.mockImplementation((_c: string, argv: string[]) =>
      child(argv[1] === 'status' ? status : '')
    );
    await run(['down']);
    const messages = info.mock.calls.map((c) => String(c[0]));
    expect(messages.some((m) => m.includes('rediacc31') && m.includes('192.168.111.31'))).toBe(
      true
    );
    expect(messages.some((m) => m.includes('rediacc1 '))).toBe(false);
  });

  it('ops down still runs when status fails', async () => {
    spawn.mockImplementation(() => child('not json'));
    await run(['down']);
    expect(spawn.mock.calls.some((c) => (c[1] as string[])[1] === 'down')).toBe(true);
  });
});
