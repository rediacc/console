import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const createCloudMachine = vi.fn(async () => undefined);

vi.mock('../../services/tofu/index.js', () => ({
  createCloudMachine: (...args: unknown[]) => createCloudMachine(...(args as [])),
  destroyCloudMachine: vi.fn(),
}));

import { registerCloudCommands } from '../machine/provision.js';

async function run(args: string[]): Promise<Record<string, unknown>> {
  const program = new Command();
  const machine = program.command('machine');
  registerCloudCommands(machine, program);
  await program.parseAsync(['node', 'rdc', 'machine', 'provision', 'dr-mail', ...args]);
  return (createCloudMachine.mock.calls[0] as unknown[])[2] as Record<string, unknown>;
}

describe('machine provision --no-infra', () => {
  beforeEach(() => createCloudMachine.mockClear());

  it('passes noInfra: true so no DNS or infra push runs', async () => {
    const opts = await run(['--provider', 'p', '--no-infra']);
    expect(opts.noInfra).toBe(true);
  });

  it('leaves noInfra false when the flag is absent', async () => {
    const opts = await run(['--provider', 'p']);
    expect(opts.noInfra).toBe(false);
  });
});
