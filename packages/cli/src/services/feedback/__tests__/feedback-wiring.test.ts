/** The write sites: the post-action hook (setExitCode), handleError and the uncaught-exception handler. */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createCli } from '../../../cli.js';
import { handleError } from '../../../utils/errors.js';
import { GLOBAL_VALUE_OPTIONS } from '../redact.js';
import { readRing, uninstallStderrTap } from '../ring.js';

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
  uninstallStderrTap();
  vi.restoreAllMocks();
  vi.resetModules();
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

  it('the uncaughtException handler in index.ts records the crash', async () => {
    const handlers: Record<string, (error: unknown) => void> = {};
    vi.spyOn(process, 'on').mockImplementation(((event: string, fn: (error: unknown) => void) => {
      handlers[event] = fn;
      return process;
    }) as never);
    vi.spyOn(process, 'exit').mockImplementation((() => undefined) as never);
    vi.doMock('../../../cli.js', () => ({ cli: { parseAsync: () => Promise.resolve() } }));
    vi.doMock('../../telemetry/telemetry.js', () => ({
      telemetryService: {
        trackError: () => undefined,
        shutdown: () => Promise.resolve(),
        stopProfiling: () => Promise.resolve(),
      },
    }));
    vi.doMock('../../update/background-updater.js', () => ({
      applyPendingUpdate: () => Promise.resolve(),
      maybeSpawnBackgroundUpdate: () => Promise.resolve(),
      runBackgroundUpdateWorker: () => Promise.resolve(),
    }));
    process.argv = ['node', 'rdc', 'config', 'init', 'x'];
    await import('../../../index.js');
    handlers.uncaughtException(new Error('crash password=hunter2hunter2'));
    const [entry] = readRing();
    expect(entry.errorCode).toBe('UNCAUGHT_EXCEPTION');
    expect(entry.errorMessage).not.toContain('hunter2');
    expect(entry.argv).toBe('config init x');
    vi.doUnmock('../../../cli.js');
    vi.doUnmock('../../telemetry/telemetry.js');
    vi.doUnmock('../../update/background-updater.js');
  }, 30_000);

  it('the root options list matches the value-taking options of createCli', () => {
    const live = createCli()
      .options.filter((o) => o.required || o.optional)
      .flatMap((o) => [o.short, o.long])
      .filter((f): f is string => f !== undefined);
    const byName = (a: string, b: string) => a.localeCompare(b);
    expect([...GLOBAL_VALUE_OPTIONS].sort(byName)).toEqual(live.sort(byName));
  });
});
