/**
 * An agent's command sent through `--proxy` meets the agent rules of `decide` on this side of the
 * wire (agent/plans/PLAN-rmcp-decide.md D22). The executor sees only the account (here an owner of
 * an org with no policy, which `decide` lets change a grand repo), never whether an agent typed
 * the command, so the opt-in a human set is asked for before the request leaves. A proxy client
 * holds no config: the ref is unresolved and counts as grand.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CliExitError } from '../utils/cli-exit-error.js';

const m = vi.hoisted(() => ({
  throughProxy: vi.fn(),
  isAgent: vi.fn(() => true),
  legit: vi.fn(() => true),
}));

vi.mock('../services/executor/proxy-command.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/executor/proxy-command.js')>()),
  runCommandThroughProxy: m.throughProxy,
}));
vi.mock('../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../utils/agent-guard.js')>()),
  isAgentEnvironment: m.isAgent,
}));
vi.mock('../utils/process-ancestry.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../utils/process-ancestry.js')>()),
  isOverrideLegitimate: m.legit,
}));
// No repo in the client's config, off the ops VM fleet.
vi.mock('../services/config/config-resources.js', async (importOriginal) => {
  const real = await importOriginal<typeof import('../services/config/config-resources.js')>();
  real.configService.getRepository = vi.fn(() => Promise.resolve(undefined)) as never;
  return real;
});
vi.mock('../utils/ops-vm.js', () => ({
  isOpsVmPlacement: vi.fn(() => Promise.resolve(false)),
  isOpsVmMachine: vi.fn(() => Promise.resolve(false)),
}));

const { createCli } = await import('../cli.js');

const saved = { ...process.env };
beforeEach(() => {
  delete process.env.REDIACC_ALLOW_GRAND_REPO;
  delete process.env.REDIACC_ALLOW_CLUSTER_OPS;
  m.isAgent.mockReturnValue(true);
  // The real send never returns (it ends the process); a sentinel stops the local action the same way.
  m.throughProxy.mockRejectedValue(new Error('SENT'));
});
afterEach(() => {
  process.env = { ...saved };
  vi.clearAllMocks();
});

const run = (args: string[]) =>
  createCli().parseAsync(['node', 'rdc', '--proxy', 'https://executor.test', ...args]);

describe('an agent command sent through --proxy', () => {
  it('is refused on a grand target with no human opt-in, and never reaches the executor', async () => {
    const refused = await run(['repo', 'up', 'shop']).catch((e: unknown) => e);
    expect(refused).toBeInstanceOf(CliExitError);
    expect((refused as CliExitError).details).toContain('AGENT_OPT_IN_MISSING');
    expect(m.throughProxy).not.toHaveBeenCalled();
  });

  it('is refused for a cluster operation with no cluster opt-in', async () => {
    const refused = await run(['cluster', 'evict', 'node-1']).catch((e: unknown) => e);
    expect((refused as CliExitError).details).toContain('AGENT_OPT_IN_MISSING');
    expect(m.throughProxy).not.toHaveBeenCalled();
  });

  it('control: a human-set opt-in naming the repo lets a non-destructive command through', async () => {
    // repo promote: proxyable, grand-guarded, not destructive, so the opt-in alone clears it.
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop:test';
    await expect(run(['repo', 'promote', 'shop:test'])).rejects.toThrow('SENT');
    expect(m.throughProxy).toHaveBeenCalledOnce();
  });

  it('control: a human caller is not judged here (the executor judges the account)', async () => {
    m.isAgent.mockReturnValue(false);
    await expect(run(['repo', 'up', 'shop'])).rejects.toThrow('SENT');
    expect(m.throughProxy).toHaveBeenCalledOnce();
  });
});
