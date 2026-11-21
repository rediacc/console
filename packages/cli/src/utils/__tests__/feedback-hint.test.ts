/** The failure hint, driven through the real entry point (tsx) with stdout and stderr read separately. */
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createCli } from '../../cli.js';
import { feedbackHint, shouldHint, withFeedbackOption } from '../../services/feedback/hint.js';
import { uninstallStderrTap } from '../../services/feedback/ring.js';

const HINT = 'Unexpected? rdc feedback report --last';
const cliRoot = path.resolve(import.meta.dirname, '..', '..', '..');
let home: string;

beforeEach(() => {
  home = mkdtempSync(path.join(tmpdir(), 'feedback-hint-'));
});
afterEach(() => {
  rmSync(home, { recursive: true, force: true });
});

function restoreEnv(key: string, saved: string | undefined): void {
  if (saved === undefined) Reflect.deleteProperty(process.env, key);
  else process.env[key] = saved;
}

function run(args: string[], env: Record<string, string> = {}) {
  const base: Record<string, string | undefined> = { ...process.env };
  delete base.REDIACC_FEEDBACK_HINT;
  const r = spawnSync('npx', ['tsx', 'src/index.ts', ...args], {
    cwd: cliRoot,
    encoding: 'utf8',
    env: {
      ...base,
      XDG_STATE_HOME: path.join(home, 'state'),
      XDG_CONFIG_HOME: path.join(home, 'config'),
      ...env,
    } as NodeJS.ProcessEnv,
  });
  return { code: r.status, stdout: r.stdout, stderr: r.stderr };
}

describe('failure hint through the real entry point', () => {
  it('text mode: hint on stderr after the error, nothing on stdout', () => {
    const r = run(['repo', 'status', 'nosuch', '-o', 'table']);
    expect(r.code).toBe(5);
    expect(r.stdout).not.toContain('feedback');
    expect(r.stderr.trimEnd().endsWith(HINT)).toBe(true);
    expect(r.stderr.indexOf('Error:')).toBeLessThan(r.stderr.indexOf(HINT));
  });

  it('JSON mode: next option in errors[0], stdout is one document, stderr has no hint', () => {
    const r = run(['repo', 'status', 'nosuch', '-o', 'json']);
    const doc = JSON.parse(r.stdout);
    const runs = doc.errors[0].next.options.map((o: { run: string }) => o.run);
    expect(runs).toContain('rdc feedback report --last');
    expect(r.stderr).not.toContain(HINT);
  });

  it('REDIACC_FEEDBACK_HINT=0 removes both (control for the two tests above)', () => {
    const text = run(['repo', 'status', 'nosuch', '-o', 'table'], { REDIACC_FEEDBACK_HINT: '0' });
    expect(text.stderr).not.toContain('feedback report');
    const json = run(['repo', 'status', 'nosuch', '-o', 'json'], { REDIACC_FEEDBACK_HINT: '0' });
    expect(JSON.parse(json.stdout).errors[0].next).toBeUndefined();
  });

  it('a usage error prints no hint', () => {
    const r = run(['repo', 'status', 'nosuch', '--output', 'bogus']);
    expect(r.code).toBe(2);
    expect(r.stderr).not.toContain('feedback report');
  });

  it('a failing `rdc feedback` prints no hint', () => {
    const r = run(['feedback', 'nosuchverb', '-o', 'table']);
    expect(r.code).not.toBe(0);
    expect(r.stderr).not.toContain(HINT);
  });
});

describe('hint policy', () => {
  it('applies to a failing command and keeps an existing next option', () => {
    const ctx = { argv: ['repo', 'up', 'x'], exitCode: 1 };
    expect(feedbackHint(ctx)).toBe(HINT);
    const next = withFeedbackOption(
      { summary: 'Do X', options: [{ description: 'x', run: 'rdc x' }] },
      ctx
    );
    expect(next?.summary).toBe('Do X');
    expect(next?.options?.map((o) => o.run)).toEqual(['rdc x', 'rdc feedback report --last']);
  });

  it('is silent for success, usage errors, feedback and when disabled', () => {
    expect(shouldHint({ argv: ['repo', 'up'], exitCode: 0 })).toBe(false);
    expect(shouldHint({ argv: ['repo', 'up'], exitCode: 2 })).toBe(false);
    expect(shouldHint({ argv: ['--config', 'a', 'feedback', 'report'], exitCode: 1 })).toBe(false);
    const saved = process.env.REDIACC_FEEDBACK_HINT;
    process.env.REDIACC_FEEDBACK_HINT = '0';
    try {
      expect(shouldHint({ argv: ['repo', 'up'], exitCode: 1 })).toBe(false);
      expect(withFeedbackOption(undefined, { argv: ['repo'], exitCode: 1 })).toBeUndefined();
    } finally {
      restoreEnv('REDIACC_FEEDBACK_HINT', saved);
    }
  });
});

describe('setExitCode path', () => {
  afterEach(() => {
    uninstallStderrTap();
    process.exitCode = undefined;
  });

  /** Run `rdc <command> [-o json]` through createCli with process.exitCode set by the command; return what stderr got. */
  async function stderrOf(command: string, extra: string[] = []): Promise<string> {
    const writes: string[] = [];
    const orig = process.stderr.write;
    process.stderr.write = ((c: unknown) => {
      writes.push(String(c));
      return true;
    }) as typeof process.stderr.write;
    const savedArgv = process.argv;
    const savedState = process.env.XDG_STATE_HOME;
    process.env.XDG_STATE_HOME = path.join(home, 'state');
    try {
      const program = createCli();
      program.command('boom').action(() => {
        process.exitCode = 3;
      });
      program.command('fine').action(() => {});
      process.argv = ['node', 'rdc', command, ...extra];
      await program.parseAsync(process.argv);
      return writes.join('');
    } finally {
      process.stderr.write = orig;
      process.argv = savedArgv;
      restoreEnv('XDG_STATE_HOME', savedState);
    }
  }

  it('prints the hint on stderr when a command fails through process.exitCode, and not on success', async () => {
    expect(await stderrOf('fine', ['-o', 'table'])).not.toContain(HINT);
    expect(await stderrOf('boom', ['-o', 'table'])).toContain(HINT);
  });

  it('prints no hint on stderr in JSON mode, where the envelope carries it', async () => {
    expect(await stderrOf('boom', ['-o', 'json'])).not.toContain(HINT);
  });
});
