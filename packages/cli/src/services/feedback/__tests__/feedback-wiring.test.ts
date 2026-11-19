/** The write sites: the post-action hook (setExitCode), handleError and the uncaught-exception handler. */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createCli } from '../../../cli.js';
import { handleError } from '../../../utils/errors.js';
import { readRing } from '../ring.js';

let state: string;
let previous: string | undefined;
const savedArgv = process.argv;
const savedExit = process.exitCode;

beforeEach(() => {
  previous = process.env.XDG_STATE_HOME;
  state = mkdtempSync(path.join(tmpdir(), 'feedback-wiring-'));
  process.env.XDG_STATE_HOME = state;
});

afterEach(() => {
  if (previous === undefined) delete process.env.XDG_STATE_HOME;
  else process.env.XDG_STATE_HOME = previous;
  process.argv = savedArgv;
  process.exitCode = savedExit;
  rmSync(state, { recursive: true, force: true });
  vi.restoreAllMocks();
});

describe('ring buffer write sites', () => {
  it('the post-action hook records a command that failed through setExitCode', async () => {
    const program = createCli();
    program.command('boom').action(() => {
      process.exitCode = 3;
    });
    process.argv = ['node', 'rdc', 'boom'];
    await program.parseAsync(process.argv);
    const entries = readRing();
    expect(entries).toHaveLength(1);
    expect(entries[0].exitCode).toBe(3);
    expect(entries[0].argv).toBe('boom');
  }, 30_000);

  it('handleError records the error code and the scrubbed message before exiting', () => {
    vi.spyOn(process, 'exit').mockImplementation((() => {
      throw new Error('exit called');
    }) as never);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.spyOn(process.stdout, 'write').mockReturnValue(true);
    process.argv = ['node', 'rdc', 'config', 'init', 'x'];
    expect(() => handleError(new Error('boom password=hunter2hunter2'))).toThrow('exit called');
    const [entry] = readRing();
    expect(entry.errorMessage).toContain('boom');
    expect(entry.errorMessage).not.toContain('hunter2');
    expect(entry.errorCode).toBeDefined();
    expect(entry.exitCode).toBeGreaterThan(0);
  });
});
