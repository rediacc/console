/**
 * An agent's command sent through `--proxy` meets the agent rules of `decide` on this side of the
 * wire (agent/plans/PLAN-rmcp-decide.md D22). The executor sees only the account (here an owner of
 * an org with no policy, which `decide` lets change a grand repo), never whether an agent typed
 * the command, so the opt-in a human set is asked for before the request leaves. A proxy client
 * holds no config: the ref is unresolved and counts as grand. A refusal renders through
 * handleError like any action's error, so a JSON caller reads the decision code in the envelope.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
vi.mock('../utils/ops-vm.js', () => ({
  isOpsVmPlacement: vi.fn(() => Promise.resolve(false)),
  isOpsVmMachine: vi.fn(() => Promise.resolve(false)),
}));

const { createCli } = await import('../cli.js');
const { configService } = await import('../services/config/config-resources.js');

class Exited extends Error {
  constructor(readonly code: number | undefined) {
    super(`process.exit(${code})`);
  }
}

const saved = { ...process.env };
let out = '';
beforeEach(() => {
  delete process.env.REDIACC_ALLOW_GRAND_REPO;
  delete process.env.REDIACC_ALLOW_CLUSTER_OPS;
  m.isAgent.mockReturnValue(true);
  m.legit.mockReturnValue(true);
  // No repo in the client's config; spied, so the real singleton is restored after each test.
  vi.spyOn(configService, 'getRepository').mockResolvedValue(undefined);
  // The real send never returns (it ends the process); a sentinel stops the local action the same way.
  m.throughProxy.mockRejectedValue(new Error('SENT'));
  out = '';
  vi.spyOn(process.stdout, 'write').mockImplementation((chunk: unknown) => {
    out += String(chunk);
    return true;
  });
  vi.spyOn(process, 'exit').mockImplementation((code?: unknown) => {
    throw new Exited(code as number | undefined);
  });
});
afterEach(() => {
  process.env = { ...saved };
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

const run = (args: string[]) =>
  createCli().parseAsync([
    'node',
    'rdc',
    '-o',
    'json',
    '--proxy',
    'https://executor.test',
    ...args,
  ]);

/** The decision code the refusal's JSON envelope carries in its details. */
function refusalDetails(): unknown[] {
  const envelope = JSON.parse(out) as { errors?: { details?: unknown[] }[] };
  return envelope.errors?.[0]?.details ?? [];
}

async function refused(args: string[]): Promise<unknown[]> {
  await expect(run(args)).rejects.toBeInstanceOf(Exited);
  expect(m.throughProxy).not.toHaveBeenCalled();
  return refusalDetails();
}

describe('an agent command sent through --proxy', () => {
  it('is refused on a grand target with no human opt-in, and never reaches the executor', async () => {
    expect(await refused(['repo', 'up', 'shop'])).toContain('AGENT_OPT_IN_MISSING');
  });

  it('is refused for a cluster operation with no cluster opt-in', async () => {
    expect(await refused(['cluster', 'evict', 'node-1'])).toContain('AGENT_OPT_IN_MISSING');
  });

  it('is refused for a grand-guarded command naming no repo: an absent repo counts as grand', async () => {
    // repo prune with no ref surveys a whole machine; the named opt-in covers no repo of it.
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop';
    expect(await refused(['repo', 'prune', '--machine', 'node-1'])).toContain(
      'AGENT_OPT_IN_MISSING'
    );
  });

  it('control: the wildcard opt-in covers a command naming no repo', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    await expect(run(['repo', 'prune', '--machine', 'node-1'])).rejects.toThrow('SENT');
    expect(m.throughProxy).toHaveBeenCalledOnce();
  });

  it('is refused when the opt-in fails the ancestry check (the agent set it itself)', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop:test';
    m.legit.mockReturnValue(false);
    expect(await refused(['repo', 'promote', 'shop:test'])).toContain('AGENT_OPT_IN_MISSING');
  });

  it('control: a human-set opt-in naming the repo lets a non-destructive command through', async () => {
    // repo promote: proxyable, grand-guarded, not destructive, so the opt-in alone clears it.
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop:test';
    await expect(run(['repo', 'promote', 'shop:test'])).rejects.toThrow('SENT');
    expect(m.throughProxy).toHaveBeenCalledOnce();
  });

  it('asks a destructive command on a grand for confirmation even with the opt-in', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop';
    expect(await refused(['repo', 'up', 'shop'])).toContain('CONFIRMATION_REQUIRED');
  });

  it('control: --confirm-grand naming the repo confirms it', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop';
    await expect(run(['--confirm-grand', 'shop', 'repo', 'up', 'shop'])).rejects.toThrow('SENT');
    expect(m.throughProxy).toHaveBeenCalledOnce();
  });

  it('control: a human caller is not judged here (the executor judges the account)', async () => {
    m.isAgent.mockReturnValue(false);
    await expect(run(['repo', 'up', 'shop'])).rejects.toThrow('SENT');
    expect(m.throughProxy).toHaveBeenCalledOnce();
  });
});
