/**
 * `--verbose` echoes the rsync command line: on stdout in table format, on stderr under -o json/yaml/csv
 * so stdout stays the one result document. rsync is a fake child process here.
 */

import { EventEmitter } from 'node:events';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setCurrentOutputFormat } from '../../../services/core/output-format.js';

const out = vi.hoisted(() => ({ stdout: [] as string[], stderr: [] as string[] }));

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  spawn: () => {
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter;
      stderr: EventEmitter;
    };
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    setImmediate(() => child.emit('close', 0));
    return child;
  },
}));
vi.mock('../../utils/platform.js', () => ({
  commandExists: async () => true,
  getPlatform: () => 'linux',
}));
vi.mock('../../../services/core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../services/core/request-context.js')>()),
  writeStdout: (s: string) => out.stdout.push(s),
  writeStderr: (s: string) => out.stderr.push(s),
}));

import { executeRsync, getRsyncPreview } from '../rsync.js';

const run = () =>
  executeRsync({ sshOptions: '', source: '/src/', destination: 'h:/dst/', verbose: true });

afterEach(() => {
  out.stdout.length = 0;
  out.stderr.length = 0;
  setCurrentOutputFormat('table');
});

describe('executeRsync verbose command echo', () => {
  it('table format writes it to stdout (control)', async () => {
    await run();
    expect(out.stdout.join('')).toContain('[rsync] Executing');
    expect(out.stderr.join('')).not.toContain('[rsync] Executing');
  });

  it.each(['json', 'yaml', 'csv'] as const)('-o %s writes it to stderr', async (format) => {
    setCurrentOutputFormat(format);
    await run();
    expect(out.stdout).toEqual([]);
    expect(out.stderr.join('')).toContain('[rsync] Executing');
  });
});

describe('getRsyncPreview verbose command echo', () => {
  const preview = () =>
    getRsyncPreview({ sshOptions: '', source: '/src/', destination: 'h:/dst/', verbose: true });

  it('table format writes it to stdout (control)', async () => {
    await preview();
    expect(out.stdout.join('')).toContain('[rsync] Preview');
    expect(out.stderr.join('')).not.toContain('[rsync] Preview');
  });

  it.each(['json', 'yaml', 'csv'] as const)('-o %s writes it to stderr', async (format) => {
    setCurrentOutputFormat(format);
    await preview();
    expect(out.stdout).toEqual([]);
    expect(out.stderr.join('')).toContain('[rsync] Preview');
  });
});
