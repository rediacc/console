/**
 * `-b` through the proxy, MCP half (finding #d31b4054): a windowed tool offers `background`, and the
 * child `rdc` it spawns runs with `--background`, which a `--proxy` executor now honours. A tool that
 * starts no job carries no such field.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { executeRdcCommand } from '../executor.js';
import { buildAllTools } from '../tools.js';

const mockExecFile = vi.fn();
vi.mock('node:child_process', () => ({
  execFile: (...args: unknown[]) => mockExecFile(...args),
}));

const childArgs = () => mockExecFile.mock.calls[0]?.[1] as string[];
const base = { defaultTimeoutMs: 120_000 };

function childPrints(stdout: string) {
  mockExecFile.mockImplementation(
    (_cmd: string, _args: string[], _opts: unknown, callback: (...args: unknown[]) => void) =>
      callback(null, { stdout, stderr: '' })
  );
}

afterEach(() => vi.clearAllMocks());

describe('MCP background', () => {
  it('E: forwards --background to the child when asked', async () => {
    childPrints('');
    await executeRdcCommand(['repo', 'up', 'shop'], { ...base, background: true });
    expect(childArgs()).toContain('--background');
  });

  it('control: no --background unless asked', async () => {
    childPrints('');
    await executeRdcCommand(['repo', 'up', 'shop'], base);
    expect(childArgs()).not.toContain('--background');
  });

  it('every windowed tool offers background, and an unwindowed one does not', () => {
    const tools = buildAllTools();
    const windowed = tools.filter((t) => t.attachWindowMs !== undefined);
    expect(windowed.length).toBeGreaterThan(10);
    for (const tool of windowed) expect(tool.schema, tool.name).toHaveProperty('background');
    for (const tool of tools.filter((t) => t.attachWindowMs === undefined)) {
      expect(tool.schema, tool.name).not.toHaveProperty('background');
    }
  });
});
