/**
 * The MCP dispatch half of `-b`: a call to a windowed tool with `background: true` runs the child `rdc` with
 * `--background`, and nothing else does. `job-background.test.ts` covers the executor and the tool schemas; this drives
 * the registered handler, where the pass-through lives.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildAllTools, registerAllTools } from '../tools.js';

const mockExecFile = vi.fn();
vi.mock('node:child_process', () => ({
  execFile: (...args: unknown[]) => mockExecFile(...args),
}));

type Handler = (args: Record<string, unknown>) => Promise<unknown>;

function handlers(): Map<string, Handler> {
  const registered = new Map<string, Handler>();
  const server = {
    registerTool: (name: string, _definition: unknown, handler: Handler) => {
      registered.set(name, handler);
    },
  };
  registerAllTools(server as never, { defaultTimeoutMs: 120_000 });
  return registered;
}

function callTool(name: string, args: Record<string, unknown>): Promise<unknown> {
  const handler = handlers().get(name);
  if (!handler) return Promise.reject(new Error(`no handler registered for ${name}`));
  return handler(args);
}

function childPrints(): void {
  mockExecFile.mockImplementation(
    (_cmd: string, _args: string[], _opts: unknown, callback: (...args: unknown[]) => void) =>
      callback(null, { stdout: '', stderr: '' })
  );
}

const childArgs = () => mockExecFile.mock.calls[0]?.[1] as string[];

afterEach(() => vi.clearAllMocks());

describe('MCP tool dispatch with background', () => {
  const windowed = buildAllTools().find((t) => t.name === 'backup_status');
  const unwindowed = buildAllTools().find(
    (t) => t.attachWindowMs === undefined && !t.repoArgField && !t.isDestructive
  );

  it('the fixtures exist: a windowed tool and an unwindowed one', () => {
    expect(windowed?.attachWindowMs).toBeDefined();
    expect(unwindowed).toBeDefined();
  });

  it('runs the child with --background when a windowed tool is called with background: true', async () => {
    childPrints();
    await callTool('backup_status', { machine: 'm1', background: true });
    expect(childArgs()).toContain('--background');
  });

  it('control: no --background without the flag, and none for a tool that has no window', async () => {
    childPrints();
    await callTool('backup_status', { machine: 'm1' });
    expect(childArgs()).not.toContain('--background');

    mockExecFile.mockClear();
    childPrints();
    await callTool(unwindowed?.name ?? '', { machine: 'm1', background: true });
    expect(childArgs()).not.toContain('--background');
  });
});
