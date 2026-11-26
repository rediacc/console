import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const runOpsJSON = vi.fn();
const runOpsStreaming = vi.fn();

vi.mock('../../../services/executor/ops-executor.js', () => ({
  opsExecutorService: {
    runOpsJSON: (...args: unknown[]) => runOpsJSON(...args),
    runOpsStreaming: (...args: unknown[]) => runOpsStreaming(...args),
  },
}));

const { registerOpsStatusCommand } = await import('../status.js');
const { registerOpsSSHCommand } = await import('../ssh.js');
const { registerOpsUpCommand } = await import('../up.js');
const { registerOpsDownCommand } = await import('../down.js');

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
    runOpsStreaming.mockReset();
    runOpsStreaming.mockResolvedValue(0);
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
    // No VM matches the empty status list, so the handler reports vmNotFound and returns without rejecting.
    await expect(
      program(registerOpsSSHCommand).parseAsync([
        'node',
        'rdc',
        'ops',
        'ssh',
        '--vm-id',
        '11',
        '--backend',
        'hyperv',
      ])
    ).resolves.toBeDefined();
    expect(runOpsJSON).toHaveBeenCalledWith('status', [], { backend: 'hyperv' });
  });

  it('up accepts hyperv and passes it to the streaming executor', async () => {
    await program(registerOpsUpCommand).parseAsync([
      'node',
      'rdc',
      'ops',
      'up',
      '--backend',
      'hyperv',
    ]);
    expect(runOpsStreaming).toHaveBeenCalledWith('up', [], {
      backend: 'hyperv',
      debug: undefined,
    });
  });

  it('down accepts hyperv and passes it to the streaming executor', async () => {
    await program(registerOpsDownCommand).parseAsync([
      'node',
      'rdc',
      'ops',
      'down',
      '--backend',
      'hyperv',
    ]);
    expect(runOpsStreaming).toHaveBeenCalledWith('down', [], {
      backend: 'hyperv',
      debug: undefined,
    });
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
