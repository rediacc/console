/**
 * The local MCP server carries no repo guard of its own (agent/plans/PLAN-rmcp-decide.md Design 3).
 * A tool call naming a grand repo reaches the child `rdc`, which runs as an agent
 * (`REDIACC_AGENT=1`) and meets the CLI's command-policy check: one check, one answer. Before
 * this, the MCP layer refused every repo tool on a grand repo (reads and `repo fork` included)
 * while the same command typed by an agent was judged by the CLI's rules.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { registerAllTools } from '../tools.js';

const mockExecFile = vi.fn();
vi.mock('node:child_process', () => ({
  execFile: (...args: unknown[]) => mockExecFile(...args),
}));

// Every repo the config names is a grand (no grandGuid), off the ops VM fleet.
vi.mock('../../../services/config/config-resources.js', () => ({
  configService: {
    setRuntimeConfig: vi.fn(),
    getRepository: vi.fn(() =>
      Promise.resolve({ repositoryGuid: 'g-1', placement: { machine: 'prod-1' } })
    ),
  },
}));
vi.mock('../../../utils/ops-vm.js', () => ({
  isOpsVmPlacement: vi.fn(() => Promise.resolve(false)),
  isOpsVmMachine: vi.fn(() => Promise.resolve(false)),
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
