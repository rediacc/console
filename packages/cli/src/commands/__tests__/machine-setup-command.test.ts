import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installJobDeps } from './job-deps.js';

const { executed } = vi.hoisted(() => ({
  executed: [] as { functionName: string; commandKind?: unknown }[],
}));

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
  writeStderr: vi.fn(),
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
  machineConnections: { acquireFor: vi.fn(), acquire: vi.fn() },
}));

import { registerMachineRegistrationCommands } from '../machine/register.js';

let restoreJobDeps: () => void;

async function setup(...args: string[]): Promise<void> {
  const program = new Command();
  const machine = program.command('machine');
  registerMachineRegistrationCommands(machine, program);
  await program.parseAsync(['machine', 'setup', 'm1', ...args], { from: 'user' });
}

describe('machine setup command', () => {
  beforeEach(() => {
    executed.length = 0;
    // A failed job keeps the test out of the success tails; the failure tail needs a lease the mock lacks.
    restoreJobDeps = installJobDeps((options) => {
      executed.push(options);
      return Promise.resolve({ success: false, exitCode: 1, durationMs: 1, state: 'failed' });
    });
  });

  afterEach(() => {
    restoreJobDeps();
  });

  it('runs one setup command-kind job whose argument values are data, never shell words', async () => {
    await setup('--datastore-path', "/mnt/my data/o'x;y").catch(() => undefined);

    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({
      functionName: 'setup',
      commandKind: {
        name: 'setup',
        args: { datastore: "/mnt/my data/o'x;y", 'datastore-size': '95%' },
      },
    });
  });

  it('carries a hostile --datastore-size as a JSON argument value', async () => {
    await setup('--datastore-size', '50%;touch x').catch(() => undefined);

    expect(executed[0]).toMatchObject({
      commandKind: { args: { 'datastore-size': '50%;touch x' } },
    });
  });
});
