/**
 * The local MCP server carries no repo guard of its own (agent/plans/PLAN-rmcp-decide.md Design 3).
 * A tool call naming a grand repo reaches the child `rdc`, which runs as an agent
 * (`REDIACC_AGENT=1`) and meets the CLI's command-policy check: one check, one answer. Before
 * this, the MCP layer refused every repo tool on a grand repo (reads and `repo fork` included)
 * while the same command typed by an agent was judged by the CLI's rules.
 *
 * THE CHILD HALF (review aa3f2a5f.1). Spawning the child proves nothing unless the child refuses.
 * The `the child CLI` block takes the exact argv and env the MCP executor handed `execFile`, runs
 * them through the real `createCli()` in this process (agent detection reads that env), and stops
 * at the first step past the policy check: the machine dispatch (`repo-executor.js`) records that
 * it was reached instead of opening SSH. A grand-repo mutation must stop before it without the
 * opt-in, and reach it with the opt-in an operator set before the session.
 */

import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { registerAllTools } from '../tools.js';
import { FIRST_CALL_CTX } from './policy-ctx.js';

const mockExecFile = vi.fn();
vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  execFile: (...args: unknown[]) => mockExecFile(...args),
}));

// Every repo the config names is a grand (no grandGuid), off the ops VM fleet.
const child = vi.hoisted(() => {
  const grand: { repositoryGuid: string; grandGuid?: string; placement: { machine: string } } = {
    repositoryGuid: 'g-1',
    placement: { machine: 'prod-1' },
  };
  return {
    reached: vi.fn(),
    legit: vi.fn(() => true),
    grand,
    /** The repo the config answers for `shop`; a test swaps in a fork and the afterEach restores the grand. */
    current: grand,
    /** The spies on the real configService singleton, restored in afterAll (review 1dd9f055.4). */
    spies: [] as { mockRestore: () => void }[],
  };
});
vi.mock('../../../services/config/config-resources.js', async (importOriginal) => {
  const real =
    await importOriginal<typeof import('../../../services/config/config-resources.js')>();
  const service = real.configService;
  child.spies.push(
    vi.spyOn(service, 'setRuntimeConfig').mockImplementation(vi.fn() as never),
    vi
      .spyOn(service, 'getRepository')
      .mockImplementation((() => Promise.resolve(child.current)) as never),
    vi
      .spyOn(service, 'resolveDestructiveTarget')
      .mockImplementation((() => Promise.resolve({ key: 'shop', config: child.current })) as never)
  );
  return real;
});
vi.mock('../../../utils/ops-vm.js', () => ({
  isOpsVmPlacement: vi.fn(() => Promise.resolve(false)),
  isOpsVmMachine: vi.fn(() => Promise.resolve(false)),
}));
// The child is an agent exactly when the env the executor gave it says so.
vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => process.env.REDIACC_AGENT === '1',
}));
// The ancestry walk has its own suite; here it answers "the operator set the opt-in before the session".
vi.mock('../../../utils/process-ancestry.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/process-ancestry.js')>()),
  isOverrideLegitimate: child.legit,
}));
vi.mock('../../../utils/repo-target.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/repo-target.js')>()),
  resolveRepoRef: vi.fn(() =>
    Promise.resolve({ name: 'shop', repoKey: 'shop', machineName: 'prod-1', imageAbsent: false })
  ),
}));
vi.mock('../../../commands/repo-delete-machine-gone.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../commands/repo-delete-machine-gone.js')>()),
  goneMachineOf: vi.fn(() => Promise.resolve(undefined)),
}));
vi.mock('../../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn(() => Promise.resolve()),
}));
// The first machine step past the policy check, for both `repo up` and `repo delete`.
vi.mock('../../../utils/repo-executor.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/repo-executor.js')>()),
  executeRepoFunction: (...args: unknown[]) => {
    child.reached(...args);
    return Promise.reject(new Error('REACHED the machine dispatch'));
  },
  recordedDatastoreMount: (...args: unknown[]) => {
    child.reached(...args);
    return Promise.reject(new Error('REACHED the machine dispatch'));
  },
}));

type Handler = (args: Record<string, unknown>) => Promise<{ isError: boolean }>;
type Registered = (args: Record<string, unknown>, ctx: unknown) => Promise<{ isError: boolean }>;

function handler(name: string): Handler {
  const registered = new Map<string, Handler>();
  const server = {
    registerTool: (toolName: string, _definition: unknown, fn: Registered) => {
      registered.set(toolName, (args) => fn(args, FIRST_CALL_CTX));
    },
  };
  registerAllTools(server as never, { defaultTimeoutMs: 120_000 });
  const fn = registered.get(name);
  if (!fn) throw new Error(`no handler registered for ${name}`);
  return fn;
}

function childSucceeds(): void {
  mockExecFile.mockImplementation(
    (_cmd: string, _args: string[], _opts: unknown, callback: (...args: unknown[]) => void) =>
      callback(null, { stdout: '', stderr: '' })
  );
}

const childCall = () =>
  mockExecFile.mock.calls[0] as [string, string[], { env: NodeJS.ProcessEnv }] | undefined;

let savedGrand: string | undefined;
beforeEach(() => {
  savedGrand = process.env.REDIACC_ALLOW_GRAND_REPO;
  delete process.env.REDIACC_ALLOW_GRAND_REPO;
  childSucceeds();
});
afterAll(() => {
  for (const spy of child.spies) spy.mockRestore();
});
afterEach(() => {
  child.current = child.grand;
  if (savedGrand === undefined) delete process.env.REDIACC_ALLOW_GRAND_REPO;
  else process.env.REDIACC_ALLOW_GRAND_REPO = savedGrand;
  vi.clearAllMocks();
});

describe('MCP repo tools on a grand repo', () => {
  it.each([
    ['repo_up', 'up'],
    ['repo_status', 'status'],
    ['repo_fork', 'fork'],
  ])('%s hands the call to the child rdc instead of refusing it', async (tool, verb) => {
    const result = await handler(tool)({ ref: 'shop' });
    expect(result.isError).toBe(false);
    const call = childCall();
    expect(call, 'the child rdc was never started').toBeDefined();
    expect(call?.[1]).toEqual(expect.arrayContaining(['repo', verb, 'shop']));
  });

  it('control: the child runs as an agent, so the CLI check judges it', async () => {
    await handler('repo_up')({ ref: 'shop' });
    expect(childCall()?.[2].env.REDIACC_AGENT).toBe('1');
  });
});

class Exited extends Error {
  constructor(readonly code: number | undefined) {
    super(`process.exit(${code})`);
  }
}

/** Run the child exactly as the MCP executor would have spawned it, in this process. */
async function runChild(
  call: [string, string[], { env: NodeJS.ProcessEnv }]
): Promise<{ code: number | undefined; out: string }> {
  const { resolveRdcBinary } = await import('../executor.js');
  const { createCli } = await import('../../../cli.js');
  const argv = call[1].slice(resolveRdcBinary().prefixArgs.length);
  const saved = { ...process.env };
  const savedArgv = process.argv;
  process.env = { ...call[2].env };
  process.argv = ['node', 'rdc', ...argv];
  let out = '';
  const write = vi.spyOn(process.stdout, 'write').mockImplementation((chunk: unknown) => {
    out += String(chunk);
    return true;
  });
  const exit = vi.spyOn(process, 'exit').mockImplementation((code?: unknown) => {
    throw new Exited(code as number | undefined);
  });
  try {
    await createCli().parseAsync(['node', 'rdc', ...argv]);
    return { code: 0, out };
  } catch (error) {
    if (error instanceof Exited) return { code: error.code, out };
    return { code: -1, out: `${out}${String(error)}` };
  } finally {
    write.mockRestore();
    exit.mockRestore();
    process.env = saved;
    process.argv = savedArgv;
  }
}

/** The first error of the child's JSON envelope. */
function firstError(out: string): { code?: string; message?: string } {
  const envelope = JSON.parse(out) as { errors?: { code?: string; message?: string }[] };
  return envelope.errors?.[0] ?? {};
}

async function spawnedFor(
  tool: string,
  args: Record<string, unknown>
): Promise<[string, string[], { env: NodeJS.ProcessEnv }]> {
  await handler(tool)(args);
  const call = childCall();
  if (!call) throw new Error(`${tool}: the child rdc was never started`);
  return call;
}

describe('the child CLI the MCP server spawns', () => {
  it.each([
    ['repo_up', { ref: 'shop' }],
    ['repo_delete', { ref: 'shop' }],
  ])('%s on a grand repo is refused by the child without the opt-in', async (tool, args) => {
    const call = await spawnedFor(tool, args);
    expect(call[2].env.REDIACC_AGENT).toBe('1');
    expect(call[2].env.REDIACC_ALLOW_GRAND_REPO).toBeUndefined();
    const { code, out } = await runChild(call);
    expect(child.reached, `the child reached the machine: ${out}`).not.toHaveBeenCalled();
    expect(code).not.toBe(0);
    const refusal = firstError(out);
    expect(refusal.code).toBe('VALIDATION_ERROR');
    expect(refusal.message).toContain('"shop" is a grand (production) repository');
  });

  it.each([
    ['repo_up', { ref: 'shop' }],
    ['repo_delete', { ref: 'shop' }],
  ])(
    'control: %s with the operator opt-in and a confirmation passes the child check',
    async (tool, args) => {
      process.env.REDIACC_ALLOW_GRAND_REPO = 'shop';
      const call = await spawnedFor(tool, args);
      expect(call[2].env.REDIACC_ALLOW_GRAND_REPO).toBe('shop');
      // A destructive grand change needs the operator's confirmation on top of the opt-in (decide
      // rule 6); the MCP tool does not forward one yet (rmcp-local-mcp), so the test supplies it.
      const confirmed: typeof call = [call[0], [...call[1], '--confirm-grand', 'shop'], call[2]];
      const { out } = await runChild(confirmed);
      expect(child.reached, `the child stopped short: ${out}`).toHaveBeenCalled();
      expect(firstError(out).message).toBe('REACHED the machine dispatch');
    }
  );

  it.each([
    ['repo_up', { ref: 'shop' }],
    ['repo_delete', { ref: 'shop' }],
  ])('%s with the opt-in but no confirmation stops at the child check', async (tool, args) => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop';
    const { code, out } = await runChild(await spawnedFor(tool, args));
    expect(
      child.reached,
      `the child reached the machine unconfirmed: ${out}`
    ).not.toHaveBeenCalled();
    expect(code).not.toBe(0);
  });

  it('control: an opt-in the agent injected itself is still refused', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop';
    child.legit.mockReturnValueOnce(false);
    const { code, out } = await runChild(await spawnedFor('repo_up', { ref: 'shop' }));
    expect(child.reached).not.toHaveBeenCalled();
    expect(code).not.toBe(0);
    expect(firstError(out).code).toBe('VALIDATION_ERROR');
  });
});

describe('the fork-blocked check the MCP server leaves to the child (review aa3f2a5f.2)', () => {
  const fork = { repositoryGuid: 'f-1', grandGuid: 'g-1', placement: { machine: 'prod-1' } };
  const forkRefusal = (out: string) => firstError(out).message ?? '';
  /** The argv the executor would hand execFile for this command (executor.ts appends the same tail). */
  async function autostartDisable(env: NodeJS.ProcessEnv) {
    const { resolveRdcBinary } = await import('../executor.js');
    const tail = [
      'repo',
      'admin',
      'autostart',
      'disable',
      'shop',
      '--output',
      'json',
      '--yes',
      '--quiet',
    ];
    return runChild(['node', [...resolveRdcBinary().prefixArgs, ...tail], { env }]);
  }

  it('the child refuses a fork-blocked command on a fork repo, under the env the executor sets', async () => {
    child.current = fork;
    const env = { ...process.env, REDIACC_AGENT: '1' };
    const { code, out } = await autostartDisable(env);
    expect(child.reached, `the child reached the machine: ${out}`).not.toHaveBeenCalled();
    expect(code).not.toBe(0);
    expect(forkRefusal(out)).toContain('is not available on fork repositories');
  });

  it('control: the same command on the grand repo is not stopped by the fork check', async () => {
    const env = { ...process.env, REDIACC_AGENT: '1', REDIACC_ALLOW_GRAND_REPO: 'shop' };
    const { out } = await autostartDisable(env);
    expect(child.reached, `the child stopped short: ${out}`).toHaveBeenCalled();
    expect(forkRefusal(out)).not.toContain('fork repositories');
  });

  it('every MCP tool whose command is fork-blocked refuses a fork repo through the child', async () => {
    const { buildAllTools } = await import('../tools.js');
    const { COMMAND_METADATA } = await import('../../../config/command-metadata.js');
    const reachable = buildAllTools().filter(
      (tool) => COMMAND_METADATA[tool.commandPath]?.forkBlocked === true
    );
    child.current = fork;
    for (const tool of reachable) {
      const { out } = await runChild(await spawnedFor(tool.name, { ref: 'shop' }));
      expect(forkRefusal(out), tool.name).toContain('is not available on fork repositories');
    }
    // The loop above is empty while no MCP tool maps to a fork-blocked command; this pins that fact so a new one is noticed.
    expect(reachable.map((tool) => tool.name)).toEqual([]);
  });

  it('control: the real agent detection reads REDIACC_AGENT (the stub above mirrors it, review 1dd9f055.1)', async () => {
    const real = await vi.importActual<typeof import('../../../utils/agent-guard.js')>(
      '../../../utils/agent-guard.js'
    );
    const saved = process.env.REDIACC_AGENT;
    try {
      process.env.REDIACC_AGENT = '1';
      real._resetCache();
      expect(real.isAgentEnvironment()).toBe(true);
    } finally {
      if (saved === undefined) delete process.env.REDIACC_AGENT;
      else process.env.REDIACC_AGENT = saved;
      real._resetCache();
    }
  });
});
