import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const runOpsJSON = vi.fn();

vi.mock('../../../services/executor/ops-executor.js', () => ({
  opsExecutorService: { runOpsJSON: (...args: unknown[]) => runOpsJSON(...args) },
}));

const { registerOpsStatusCommand } = await import('../status.js');
const { registerOpsSSHCommand } = await import('../ssh.js');

function program(register: (ops: Command, root: Command) => void): Command {
  const root = new Command();
  root.exitOverride();
  root.configureOutput({ writeErr: () => undefined });
  register(root.command('ops'), root);
  return root;
}

describe('rdc ops --backend hyperv', () => {
  beforeEach(() => {
    runOpsJSON.mockReset();
    runOpsJSON.mockResolvedValue({ vms: [] });
  });

  it('status accepts hyperv and passes it through', async () => {
    await program(registerOpsStatusCommand).parseAsync([
      'node',
      'rdc',
      'ops',
      'status',
      '--backend',
      'hyperv',
    ]);
    expect(runOpsJSON).toHaveBeenCalledWith('status', [], { backend: 'hyperv' });
  });

  it('ssh accepts hyperv and passes it through', async () => {
    await program(registerOpsSSHCommand)
      .parseAsync(['node', 'rdc', 'ops', 'ssh', '--vm-id', '11', '--backend', 'hyperv'])
      .catch(() => undefined);
    expect(runOpsJSON).toHaveBeenCalledWith('status', [], { backend: 'hyperv' });
  });

  it('still rejects an unknown backend', async () => {
    await expect(
      program(registerOpsStatusCommand).parseAsync([
        'node',
        'rdc',
        'ops',
        'status',
        '--backend',
        'vmware',
      ])
    ).rejects.toThrow();
  });
});
