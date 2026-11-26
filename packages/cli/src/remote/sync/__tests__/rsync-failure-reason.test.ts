/**
 * What a failed rsync tells the user: its exit code (hex beside decimal for a Windows loader status) and stderr tail, the
 * `--mirror` deletion count, and the `rsync --version` probe that finds an installed rsync that cannot start.
 * rsync is a fake child process here.
 */

import { EventEmitter } from 'node:events';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fake = vi.hoisted(() => ({
  stdout: [] as string[],
  stderr: [] as string[],
  code: 0 as number | null,
  probe: undefined as undefined | { code: number | string; killed?: boolean; stderr: string },
  probeCalls: 0,
}));

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  spawn: () => {
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter;
      stderr: EventEmitter;
    };
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    setImmediate(() => {
      for (const chunk of fake.stdout) child.stdout.emit('data', Buffer.from(chunk));
      for (const chunk of fake.stderr) child.stderr.emit('data', Buffer.from(chunk));
      child.emit('close', fake.code);
    });
    return child;
  },
  execFile: (
    _cmd: string,
    _args: string[],
    _opts: unknown,
    cb: (err: Error | null, stdout: string, stderr: string) => void
  ) => {
    fake.probeCalls++;
    if (!fake.probe) {
      cb(null, 'rsync  version 3.2.7', '');
      return;
    }
    cb(Object.assign(new Error('Command failed'), fake.probe), '', fake.probe.stderr);
  },
}));
vi.mock('../../utils/platform.js', () => ({
  commandExists: async () => true,
  getPlatform: () => 'linux',
}));

import {
  executeRsync,
  formatRsyncExitCode,
  resetRsyncProbe,
  rsyncUnusableReason,
} from '../rsync.js';

const run = () => executeRsync({ sshOptions: '', source: '/src/', destination: 'h:/dst/' });

beforeEach(() => {
  resetRsyncProbe();
  fake.probeCalls = 0;
});

afterEach(() => {
  fake.stdout = [];
  fake.stderr = [];
  fake.code = 0;
  fake.probe = undefined;
});

describe('executeRsync failure detail', () => {
  it('names the exit code of a binary that dies silently (MSYS2 0xC0000135)', async () => {
    fake.code = 3221225781;
    const result = await run();
    expect(result.success).toBe(false);
    expect(result.errors.join('\n')).toContain('rsync exit code 3221225781 (0xC0000135)');
  });

  it('carries the stderr tail beside the exit code, including a code with no canned message', async () => {
    fake.code = 99;
    fake.stderr = ['one\ntwo\nthree\nfour\nfive\n', 'six: the real reason\n'];
    const text = (await run()).errors.join('\n');
    expect(text).toContain('rsync exit code 99; stderr:');
    expect(text).toContain('six: the real reason');
  });

  it('keeps the canned message for a known code', async () => {
    fake.code = 23;
    expect((await run()).errors.join('\n')).toContain('rsync exit code 23: Partial transfer');
  });

  it('control: a successful run reports no errors', async () => {
    expect((await run()).errors).toEqual([]);
  });
});

describe('executeRsync deleted count', () => {
  const runMirror = () =>
    executeRsync({ sshOptions: '', source: '/src/', destination: 'h:/dst/', mirror: true });

  it('counts itemized deletion lines of a mirror run, also when a line is split across chunks', async () => {
    fake.stdout = [
      'sending incremental file list\n*deleting   old/a.txt\n*dele',
      'ting   b.txt\r*deleting   c.txt\n',
      '>f+++++++++ real.txt\n',
    ];
    expect((await runMirror()).deleted).toBe(3);
  });

  it('a non-mirror run never reports deletions, even for a file named "deleting ..." (4f037bc9.2)', async () => {
    fake.stdout = ['sending incremental file list\ndeleting notes.txt\n'];
    expect((await run()).deleted).toBe(0);
    expect((await runMirror()).deleted).toBe(0);
  });

  it('control: a run that removes nothing counts zero', async () => {
    fake.stdout = ['sending incremental file list\nreal.txt\n'];
    expect((await run()).deleted).toBe(0);
  });
});

describe('rsyncUnusableReason', () => {
  it('is undefined for an rsync that runs', async () => {
    expect(await rsyncUnusableReason()).toBeUndefined();
  });

  it('names the exit code and stderr of an rsync that cannot start, and probes once per run', async () => {
    fake.probe = { code: 3221225781, stderr: 'rsync.exe: DLL not found\n' };
    const reason = await rsyncUnusableReason();
    expect(reason).toContain('exit code 3221225781 (0xC0000135)');
    expect(reason).toContain('DLL not found');
    await rsyncUnusableReason();
    expect(fake.probeCalls).toBe(1);
  });

  it('reports a probe that hung', async () => {
    fake.probe = { code: 'ETIMEDOUT', killed: true, stderr: '' };
    expect(await rsyncUnusableReason()).toContain('timed out');
  });
});

describe('formatRsyncExitCode', () => {
  it('leaves small codes plain and spells large ones in hex', () => {
    expect(formatRsyncExitCode(23)).toBe('23');
    expect(formatRsyncExitCode(3221225781)).toBe('3221225781 (0xC0000135)');
  });
});
