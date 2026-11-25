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

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { registerAllTools } from '../tools.js';

const mockExecFile = vi.fn();
vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  execFile: (...args: unknown[]) => mockExecFile(...args),
}));

// Every repo the config names is a grand (no grandGuid), off the ops VM fleet.
const child = vi.hoisted(() => ({
  reached: vi.fn(),
  legit: vi.fn(() => true),
  grand: { repositoryGuid: 'g-1', placement: { machine: 'prod-1' } },
}));
vi.mock('../../../services/config/config-resources.js', async (importOriginal) => {
  const real =
    await importOriginal<typeof import('../../../services/config/config-resources.js')>();
  real.configService.setRuntimeConfig = vi.fn() as never;
  real.configService.getRepository = vi.fn(() => Promise.resolve(child.grand)) as never;
  real.configService.resolveDestructiveTarget = vi.fn(() =>
    Promise.resolve({ key: 'shop', config: child.grand })
  ) as never;
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

function handler(name: string): Handler {
  const registered = new Map<string, Handler>();
  const server = {
    registerTool: (toolName: string, _definition: unknown, fn: Handler) => {
      registered.set(toolName, fn);
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
afterEach(() => {
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
  ])('control: %s with the operator opt-in passes the child check', async (tool, args) => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'shop';
    const call = await spawnedFor(tool, args);
    expect(call[2].env.REDIACC_ALLOW_GRAND_REPO).toBe('shop');
    const { out } = await runChild(call);
    expect(child.reached, `the child stopped short: ${out}`).toHaveBeenCalled();
    expect(firstError(out).message).toBe('REACHED the machine dispatch');
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
