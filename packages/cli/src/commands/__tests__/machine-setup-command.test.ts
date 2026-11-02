import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { execCalls } = vi.hoisted(() => ({ execCalls: [] as string[] }));

vi.mock('../../i18n/index.js', () => ({ t: (k: string) => k }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getLocalConfig: vi.fn().mockResolvedValue({ sshPrivateKey: 'key', ssh: {} }),
    getLocalMachine: vi.fn().mockResolvedValue({ ip: '10.0.0.1' }),
  },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), error: vi.fn(), success: vi.fn(), warn: vi.fn() },
}));
vi.mock('../../services/core/request-context.js', () => ({
  setExitCode: vi.fn(),
  writeStdout: vi.fn(),
  // errors.ts extends DispatchExit (DispatchFailure), so the mock must carry it.
  DispatchExit: class extends Error {},
  currentRequestContext: vi.fn(),
  exitProcess: vi.fn(),
}));
vi.mock('../../services/machine/machine-remove-guard.js', () => ({ guardMachineRemoval: vi.fn() }));
vi.mock('../../services/provision/infra-provision.js', () => ({ pushInfraConfig: vi.fn() }));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({ deployAllRepoKeys: vi.fn() }));
vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  handleError: (e: unknown) => {
    throw e;
  },
}));
vi.mock('../../services/renet/renet-execution.js', () => ({
  acquireRemoteRenet: vi.fn().mockResolvedValue({
    remotePath: "/opt/my renet/o'brien;rm -rf x/renet",
    uploaded: false,
  }),
  readSSHKey: vi.fn(),
}));
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: {
    acquireFor: vi.fn().mockResolvedValue({
      release: vi.fn(),
      sftp: {
        // Non-zero keeps the test out of the post-setup tasks.
        execStreaming: vi.fn((cmd: string) => {
          execCalls.push(cmd);
          return Promise.resolve(1);
        }),
      },
    }),
  },
}));

import { registerMachineRegistrationCommands } from '../machine/register.js';

describe('machine setup command', () => {
  beforeEach(() => {
    execCalls.length = 0;
  });

  it('quotes the renet path and --datastore-path', async () => {
    const program = new Command();
    const machine = program.command('machine');
    registerMachineRegistrationCommands(machine, program);
    await program.parseAsync(['machine', 'setup', 'm1', '--datastore-path', "/mnt/my data/o'x;y"], {
      from: 'user',
    });
    expect(execCalls).toHaveLength(1);
    expect(execCalls[0]).toMatch(
      /^sudo '\/opt\/my renet\/o'\\''brien;rm -rf x\/renet' setup --auto --datastore '\/mnt\/my data\/o'\\''x;y' --datastore-size '95%'$/
    );
  });

  it('quotes a hostile --datastore-size', async () => {
    const program = new Command();
    const machine = program.command('machine');
    registerMachineRegistrationCommands(machine, program);
    await program.parseAsync(['machine', 'setup', 'm1', '--datastore-size', '50%;touch x'], {
      from: 'user',
    });
    expect(execCalls).toHaveLength(1);
    expect(execCalls[0]).toMatch(/ --datastore-size '50%;touch x'$/);
  });
});
