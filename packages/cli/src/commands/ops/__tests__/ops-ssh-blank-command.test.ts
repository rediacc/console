import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const runOpsJSON = vi.fn();
const spawn = vi.fn();
const handleError = vi.fn();

vi.mock('node:child_process', () => ({ spawn: (...args: unknown[]) => spawn(...args) }));
vi.mock('../../../services/executor/ops-executor.js', () => ({
  opsExecutorService: { runOpsJSON: (...args: unknown[]) => runOpsJSON(...args) },
}));
vi.mock('../../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/errors.js')>()),
  handleError: (e: unknown) => handleError(e),
}));

const { registerOpsSSHCommand } = await import('../ssh.js');

function program(): Command {
  const root = new Command();
  root.exitOverride();
  const ops = root.command('ops');
  registerOpsSSHCommand(ops, root);
  return root;
}

describe('rdc ops ssh -c', () => {
  beforeEach(() => {
    runOpsJSON.mockReset();
    spawn.mockReset();
    handleError.mockReset();
  });

  // An empty -c is falsy to `if (options.command)` and opened an interactive ssh session that waits on stdin.
  it.each(['', '   '])('refuses a blank command %j before any VM lookup or ssh', async (cmd) => {
    await program().parseAsync(['node', 'rdc', 'ops', 'ssh', '--vm-id', '11', '-c', cmd]);
    expect(handleError).toHaveBeenCalledTimes(1);
    expect(String((handleError.mock.calls[0] as unknown[])[0])).toMatch(/-c command is empty/);
    expect(runOpsJSON).not.toHaveBeenCalled();
    expect(spawn).not.toHaveBeenCalled();
  });

  it('runs a real command through ssh', async () => {
    runOpsJSON.mockResolvedValue({ vms: [{ id: 11, ip: '192.168.111.11', status: 'running' }] });
    spawn.mockReturnValue({ on: vi.fn() });
    await program().parseAsync(['node', 'rdc', 'ops', 'ssh', '--vm-id', '11', '-c', 'uptime']);
    expect(handleError).not.toHaveBeenCalled();
    expect(spawn).toHaveBeenCalledTimes(1);
    expect((spawn.mock.calls[0] as unknown[])[1]).toEqual(expect.arrayContaining(['--', 'uptime']));
  });
});
