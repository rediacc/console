/**
 * The CLI's one enforcement point (agent/plans/PLAN-rmcp-decide.md Design 3): the root
 * `preAction` hook judges every local command once, before its action runs, with the target read
 * off the parsed arguments through the contract bindings. Driven through `createCli` so the
 * binding of each command (repo ref positional, machine option, cluster or datastore positional)
 * is the real one. A refusal renders through handleError as a JSON envelope; an allowed command
 * reaches its action, which a sentinel stops.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  isAgent: vi.fn(() => true),
  reached: vi.fn(),
}));

vi.mock('../agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../agent-guard.js')>()),
  isAgentEnvironment: m.isAgent,
}));
vi.mock('../process-ancestry.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../process-ancestry.js')>()),
  isOverrideLegitimate: vi.fn(() => true),
}));
vi.mock('../ops-vm.js', () => ({
  isOpsVmPlacement: vi.fn(() => Promise.resolve(false)),
  isOpsVmMachine: vi.fn(() => Promise.resolve(false)),
}));
// Every repo action resolves its ref first: reaching it means the hook let the command through.
vi.mock('../repo-target.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../repo-target.js')>()),
  resolveRepoRef: vi.fn(() => {
    m.reached();
    throw new Error('REACHED the action');
  }),
}));

const { createCli } = await import('../../cli.js');
const { configService } = await import('../../services/config/config-resources.js');
const { configFileStorage } = await import('../../adapters/config-file-storage.js');

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
  vi.spyOn(configFileStorage, 'exists').mockResolvedValue(false);
  vi.spyOn(configService, 'getRepository').mockResolvedValue({ repositoryGuid: 'g-1' });
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
  createCli()
    .parseAsync(['node', 'rdc', '-o', 'json', ...args])
    .catch((e: unknown) => e);

/** The decision code of the refusal envelope, or undefined when the hook let the command through. */
function decisionCode(): unknown {
  if (!out.trim()) return undefined;
  const envelope = JSON.parse(out) as { errors?: { details?: unknown[] }[] };
  return envelope.errors?.[0]?.details?.[0];
}

describe('the root hook judges a local command before its action', () => {
  it('refuses an agent changing a grand named by the ref positional', async () => {
    await run(['repo', 'up', 'shop']);
    expect(decisionCode()).toBe('AGENT_OPT_IN_MISSING');
    expect(m.reached).not.toHaveBeenCalled();
  });

  it('judges `repo prune` in the hook: an agent naming a grand is refused, an opt-in lets it on', async () => {
    await run(['repo', 'prune', 'shop']);
    expect(decisionCode()).toBe('AGENT_OPT_IN_MISSING');
    out = '';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop';
    await run(['repo', 'prune', 'shop']);
    expect(decisionCode()).not.toBe('AGENT_OPT_IN_MISSING');
  });

  it('control: the same command on a fork reaches the action', async () => {
    vi.mocked(configService.getRepository).mockResolvedValue({
      repositoryGuid: 'f-1',
      grandGuid: 'g-1',
    });
    await run(['repo', 'up', 'shop:t']);
    expect(m.reached).toHaveBeenCalled();
  });

  it('refuses a batch form that names no repo: an absent repo counts as grand', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop';
    await run(['repo', 'up', '--all', '--machine', 'node-1']);
    expect(decisionCode()).toBe('AGENT_OPT_IN_MISSING');
  });

  it('refuses `rdc run` to an agent outright', async () => {
    await run(['run', '-f', 'some_function', '-m', 'node-1']);
    expect(decisionCode()).toBe('AGENT_BLOCKED');
  });

  it('reads the cluster opt-in subject off the datastore positional', async () => {
    process.env.REDIACC_ALLOW_CLUSTER_OPS = 'other';
    await run(['datastore', 'delete', 'ds1', '--yes']);
    expect(decisionCode()).toBe('AGENT_OPT_IN_MISSING');
    out = '';
    process.env.REDIACC_ALLOW_CLUSTER_OPS = 'ds1';
    await run(['datastore', 'delete', 'ds1', '--yes']);
    expect(decisionCode()).not.toBe('AGENT_OPT_IN_MISSING');
  });

  it('asks for confirmation of a destructive change, and --confirm-grand gives it', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop';
    await run(['repo', 'up', 'shop']);
    expect(decisionCode()).toBe('CONFIRMATION_REQUIRED');
    expect(m.reached).not.toHaveBeenCalled();
    out = '';
    await run(['--confirm-grand', 'shop', 'repo', 'up', 'shop']);
    expect(m.reached).toHaveBeenCalled();
  });

  it('leaves a command on ACTION_RESOLVED_TARGETS to its action', async () => {
    // repo promote resolves the grand the fork replaces inside its action.
    await run(['repo', 'promote', 'shop:t']);
    expect(decisionCode()).not.toBe('AGENT_OPT_IN_MISSING');
  });

  it('control: a human with no policy reaches the action without a decision', async () => {
    m.isAgent.mockReturnValue(false);
    await run(['repo', 'up', 'shop']);
    expect(m.reached).toHaveBeenCalled();
    expect(configService.getRepository).not.toHaveBeenCalled();
  });
});
