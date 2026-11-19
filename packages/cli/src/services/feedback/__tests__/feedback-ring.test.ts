import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  type CommandRequestContext,
  createOutputState,
  runInRequestContext,
} from '../../core/request-context.js';
import { redactArgv, resolveCommandPath } from '../redact.js';
import { readRing, recordCommand, resetStderrTail, RING_CAPACITY, ringFilePath } from '../ring.js';

const SECRET = 'rdt_abcdef0123456789SECRETVALUE';
let state: string;
let previous: string | undefined;

beforeEach(() => {
  previous = process.env.XDG_STATE_HOME;
  state = mkdtempSync(path.join(tmpdir(), 'feedback-ring-'));
  process.env.XDG_STATE_HOME = state;
  resetStderrTail();
});

afterEach(() => {
  if (previous === undefined) delete process.env.XDG_STATE_HOME;
  else process.env.XDG_STATE_HOME = previous;
  rmSync(state, { recursive: true, force: true });
  vi.restoreAllMocks();
});

describe('redactArgv', () => {
  it('masks a sensitive option value in both spellings', () => {
    expect(redactArgv(['subscription', 'login', '--token', SECRET])).toBe(
      'subscription login --token <redacted>'
    );
    expect(redactArgv(['subscription', 'login', `--token=${SECRET}`])).toBe(
      'subscription login --token=<redacted>'
    );
    expect(redactArgv(['subscription', 'login', '-t', SECRET])).toBe(
      'subscription login -t <redacted>'
    );
  });

  it('keeps an ordinary option value', () => {
    expect(redactArgv(['config', 'init', 'work'])).toBe('config init work');
  });

  it('fails closed on an option the contract does not know when its name is sensitive', () => {
    expect(redactArgv(['nonesuch', '--api-password', 'hunter2hunter2'])).toBe(
      'nonesuch --api-password <redacted>'
    );
  });

  it('runs the free-text scrubber over what is left', () => {
    expect(redactArgv(['config', 'init', 'https://example.com/x'])).not.toContain('example.com');
  });

  it('resolves the longest command path', () => {
    expect(resolveCommandPath(['subscription', '--debug', 'login', 'x'])).toEqual([
      'subscription',
      'login',
    ]);
    expect(resolveCommandPath(['nonesuch'])).toEqual([]);
  });
});

describe('recordCommand', () => {
  it('keeps exactly the last 10 entries, newest last, at mode 0600 under XDG_STATE_HOME', () => {
    for (let i = 0; i < RING_CAPACITY + 3; i++) {
      recordCommand({ argv: ['config', 'init', `n${i}`], exitCode: i });
    }
    const entries = readRing();
    expect(entries).toHaveLength(RING_CAPACITY);
    expect(entries.map((e) => e.exitCode)).toEqual([3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
    expect(ringFilePath().startsWith(state)).toBe(true);
    expect(statSync(ringFilePath()).mode & 0o777).toBe(0o600);
  });

  it('keeps mode 0600 when the file pre-exists with a wider mode', () => {
    mkdirSync(path.dirname(ringFilePath()), { recursive: true });
    writeFileSync(ringFilePath(), '', { mode: 0o644 });
    recordCommand({ argv: ['config', 'init'], exitCode: 1 });
    expect(statSync(ringFilePath()).mode & 0o777).toBe(0o600);
  });

  it('never writes a sensitive option value or a token in an error message', () => {
    recordCommand({
      argv: ['subscription', 'login', '--token', SECRET],
      exitCode: 1,
      errorCode: 'AUTH_REQUIRED',
      errorMessage: `login failed for ${SECRET} password=hunter2hunter2`,
    });
    const bytes = readFileSync(ringFilePath(), 'utf8');
    expect(bytes).not.toContain('SECRETVALUE');
    expect(bytes).not.toContain('hunter2');
    expect(bytes).toContain('<redacted>');
    const [entry] = readRing();
    expect(entry.commandPath).toBe('subscription login');
    expect(entry.errorCode).toBe('AUTH_REQUIRED');
  });

  it('scrubs the captured stderr tail and bounds it to 4 KB', async () => {
    const { installStderrTap } = await import('../ring.js');
    installStderrTap();
    process.stderr.write(`noise ${'x '.repeat(5000)}\nleaked ${SECRET}\n`);
    recordCommand({ argv: ['config', 'init'], exitCode: 1 });
    const [entry] = readRing();
    expect(entry.stderrTail.length).toBeLessThanOrEqual(4096);
    expect(entry.stderrTail).toContain('leaked');
    expect(entry.stderrTail).not.toContain('SECRETVALUE');
  });

  it('swallows a failed write and returns normally', () => {
    // The state dir's `feedback` slot is a regular file, so mkdir fails.
    mkdirSync(path.join(state, 'rediacc'), { recursive: true });
    writeFileSync(path.join(state, 'rediacc', 'feedback'), 'in the way');
    const before = process.exitCode;
    expect(() => recordCommand({ argv: ['config', 'init'], exitCode: 7 })).not.toThrow();
    expect(process.exitCode).toBe(before);
    expect(readRing()).toEqual([]);
  });

  it('does not record inside an executor request or for the feedback command itself', async () => {
    const ctx: CommandRequestContext = {
      output: createOutputState(),
      stdout: [],
      stderr: [],
    };
    await runInRequestContext(ctx, () => {
      recordCommand({ argv: ['config', 'init'], exitCode: 1 });
      return Promise.resolve();
    });
    expect(readRing()).toEqual([]);
    recordCommand({ argv: ['config', 'init'], exitCode: 1 });
    expect(readRing()).toHaveLength(1);
    rmSync(ringFilePath());
    recordCommand({ argv: ['feedback', 'report', '--last'], exitCode: 1 });
    expect(readRing()).toEqual([]);
  });
});
