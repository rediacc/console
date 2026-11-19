import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  type CommandRequestContext,
  createOutputState,
  runInRequestContext,
} from '../../core/request-context.js';
import { writeStderr } from '../../core/request-context.js';
import { redactArgv, resolveCommandPath } from '../redact.js';
import {
  installStderrTap,
  RING_CAPACITY,
  readRing,
  recordCommand,
  resetStderrTail,
  ringFilePath,
  uninstallStderrTap,
} from '../ring.js';

const SECRET = 'rdt_abcdef0123456789SECRETVALUE';
let state: string;
let previous: string | undefined;

beforeEach(() => {
  previous = process.env.XDG_STATE_HOME;
  state = mkdtempSync(path.join(tmpdir(), 'feedback-ring-'));
  process.env.XDG_STATE_HOME = state;
  resetStderrTail();
  vi.spyOn(process.stderr, 'write').mockReturnValue(true);
});

afterEach(() => {
  if (previous === undefined) delete process.env.XDG_STATE_HOME;
  else process.env.XDG_STATE_HOME = previous;
  rmSync(state, { recursive: true, force: true });
  uninstallStderrTap();
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

  it('masks a sensitive value that follows a root option placed before the command', () => {
    expect(redactArgv(['--config', 'work', 'subscription', 'login', '--token', SECRET])).toBe(
      '--config work subscription login --token <redacted>'
    );
    expect(redactArgv(['-o', 'json', 'subscription', 'login', `--token=${SECRET}`])).toBe(
      '-o json subscription login --token=<redacted>'
    );
    expect(resolveCommandPath(['--config', 'work', 'config', 'init'])).toEqual(['config', 'init']);
  });

  it('masks an attached short option value and keeps an attached non-sensitive one', () => {
    expect(redactArgv(['subscription', 'login', `-t${SECRET}`])).toBe(
      'subscription login -t<redacted>'
    );
    expect(redactArgv(['subscription', 'login', `-t=${SECRET}`])).toBe(
      'subscription login -t<redacted>'
    );
    expect(redactArgv(['config', 'init', '-qy'])).toBe('config init -qy');
  });

  it('masks the value of an unknown sensitive option even when it starts with a dash', () => {
    expect(redactArgv(['nonesuch', '--api-password', '-hunter2hunter2'])).toBe(
      'nonesuch --api-password <redacted>'
    );
    expect(redactArgv(['nonesuch', '--api-password', '--verbose'])).toBe(
      'nonesuch --api-password --verbose'
    );
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

  it('scrubs the captured stderr tail and bounds it to 4 KB', () => {
    installStderrTap();
    writeStderr(`noise ${'x '.repeat(5000)}\nleaked ${SECRET}\n`);
    recordCommand({ argv: ['config', 'init'], exitCode: 1 });
    const [entry] = readRing();
    expect(entry.stderrTail.length).toBeLessThanOrEqual(4096);
    expect(entry.stderrTail).toContain('leaked');
    expect(entry.stderrTail).not.toContain('SECRETVALUE');
  });

  it('scrubs a secret that straddles the 4 KB cut of the stderr tail', () => {
    installStderrTap();
    writeStderr(`start ${SECRET} ${'z'.repeat(4078)}\n`);
    recordCommand({ argv: ['config', 'init'], exitCode: 1 });
    const [entry] = readRing();
    expect(entry.stderrTail).not.toContain('ECRETVALUE');
    expect(entry.stderrTail.length).toBeLessThanOrEqual(4096);
  });

  it('skips the feedback command typed after a root option', () => {
    recordCommand({ argv: ['--config', 'work', 'feedback', 'report', '--last'], exitCode: 1 });
    expect(readRing()).toEqual([]);
    recordCommand({ argv: ['--config', 'work', 'config', 'init'], exitCode: 1 });
    expect(readRing()).toHaveLength(1);
  });

  it('the tap leaves process.stderr.write unpatched, and uninstalling stops the capture', () => {
    const original = process.stderr.write;
    installStderrTap();
    expect(process.stderr.write).toBe(original);
    uninstallStderrTap();
    writeStderr('after uninstall\n');
    recordCommand({ argv: ['config', 'init'], exitCode: 1 });
    expect(readRing()[0].stderrTail).not.toContain('after uninstall');
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
