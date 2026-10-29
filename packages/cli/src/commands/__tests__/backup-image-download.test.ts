/**
 * `rdc backup download` against fakes: a recording export session and a fake rsync runner.
 *
 * The API C1 implements in commands/backup-image.ts is pinned by the interfaces below:
 * `runDownload(options, deps)` takes every side effect through `deps`, throws for a usage or
 * environment refusal (missing --to directory, missing rsync) and returns `{ exitCode, results }`
 * for per-repo outcomes. The module is imported through a runtime path and typed by the local
 * interfaces below, so the type check of these tests does not follow the command's exports; at
 * run time the module and its whole import graph load as usual.
 */

import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { localImagePaths, readImageState } from '../../services/backup-image/state.js';

interface Ready {
  snapshot: string;
  guid: string;
  takenAt: string;
  apparentBytes: number;
  allocatedBytes: number;
  rsyncPath: string;
  lowPriority: string[];
}
interface ExportSession {
  ready: Ready;
  ping(): Promise<boolean>;
  sha256(): Promise<string>;
  quit(): Promise<void>;
}
interface ImageTarget {
  repo: string;
  tag: string;
  machine: string;
  guid: string;
  grandGuid: string | null;
  datastore: string;
}
interface RsyncRequest {
  args: string[];
  source: string;
  dest: string;
}
interface RsyncOutcome {
  exitCode: number;
  literalBytes: number;
  matchedBytes: number;
}
interface DownloadDeps {
  assertRsyncCapable(): Promise<void>;
  resolveTargets(
    refs: string[],
    opts: { all?: string; includeForks?: boolean }
  ): Promise<ImageTarget[]>;
  openSession(target: ImageTarget): Promise<ExportSession>;
  runRsync(req: RsyncRequest): Promise<RsyncOutcome>;
  hashFile(path: string): Promise<string>;
  sleep(ms: number): Promise<void>;
  now(): Date;
  write(text: string): void;
  signal?: AbortSignal;
}
interface DownloadOptions {
  to: string;
  refs: string[];
  config: string;
  retries?: number;
  skipVerify?: boolean;
  skipSpaceCheck?: boolean;
  output?: 'human' | 'json';
}
interface DownloadResult {
  repo: string;
  status: 'complete' | 'incomplete' | 'failed';
  verify?: string;
  image: string;
  error?: string;
}
interface Module {
  selectAllTargets(
    listed: { key: string; isGrand: boolean }[],
    opts: { all: string; includeForks?: boolean },
    resolve: (key: string) => Promise<ImageTarget>
  ): Promise<ImageTarget[]>;
  runDownload(
    o: DownloadOptions,
    d: DownloadDeps
  ): Promise<{ exitCode: number; results: DownloadResult[] }>;
}

const load = (): Promise<Module> =>
  import(/* @vite-ignore */ fileURLToPath(new URL('../backup-image.ts', import.meta.url)));

const target: ImageTarget = {
  repo: 'mail',
  tag: 'latest',
  machine: 'hostinger',
  guid: 'g-1',
  grandGuid: null,
  datastore: '/mnt/rediacc',
};
const DIGEST = 'cd'.repeat(32);

let to: string;
let calls: string[];
let opened: number;
let quits: number;

function fakeSession(opts: { pingOk?: boolean; sha?: string } = {}): ExportSession {
  return {
    ready: {
      snapshot: '/mnt/rediacc/repositories/.snapshot-g-1-x',
      guid: 'g-1',
      takenAt: '2026-10-29T10:00:00Z',
      apparentBytes: 1024,
      allocatedBytes: 512,
      rsyncPath: '/usr/bin/rsync',
      lowPriority: [],
    },
    ping: async () => opts.pingOk ?? true,
    sha256: async () => opts.sha ?? DIGEST,
    quit: () => {
      quits += 1;
      calls.push('quit');
      return Promise.resolve();
    },
  };
}

function baseDeps(over: Partial<DownloadDeps> = {}): DownloadDeps & { out: string[] } {
  const out: string[] = [];
  return {
    out,
    assertRsyncCapable: async () => undefined,
    resolveTargets: async () => [target],
    openSession: () => {
      opened += 1;
      calls.push('open');
      return Promise.resolve(fakeSession());
    },
    runRsync: (req) => {
      calls.push('rsync');
      writeFileSync(req.dest, 'image');
      return Promise.resolve({ exitCode: 0, literalBytes: 10, matchedBytes: 20 });
    },
    hashFile: async () => DIGEST,
    sleep: async () => undefined,
    now: () => new Date('2026-10-29T10:00:00Z'),
    write: (t) => out.push(t),
    ...over,
  };
}

const opts = (over: Partial<DownloadOptions> = {}): DownloadOptions => ({
  to,
  refs: ['mail'],
  config: 'eu-remote',
  skipSpaceCheck: true,
  ...over,
});

const paths = () => localImagePaths(to, 'hostinger', 'mail', 'latest');

beforeEach(() => {
  to = mkdtempSync(join(tmpdir(), 'dl-'));
  calls = [];
  opened = 0;
  quits = 0;
});
afterEach(() => {
  rmSync(to, { recursive: true, force: true });
});

describe('selectAllTargets (9c3f5e10.2)', () => {
  const listed = [
    { key: 'mail', isGrand: true },
    { key: 'other', isGrand: true },
  ];

  it('skips a repo placed on another machine without a word', async () => {
    const m = await load();
    const out = await m.selectAllTargets(listed, { all: 'hostinger' }, (key) =>
      Promise.resolve({ ...target, repo: key, machine: key === 'mail' ? 'hostinger' : 'elsewhere' })
    );
    expect(out.map((t) => t.repo)).toEqual(['mail']);
  });

  it('skips a repo whose datastore is detached (no machine)', async () => {
    const m = await load();
    const { CliExitError } = await import('../../utils/cli-exit-error.js');
    const out = await m.selectAllTargets(listed, { all: 'hostinger' }, (key) =>
      key === 'other'
        ? Promise.reject(new CliExitError('DETACHED', 'datastore detached'))
        : Promise.resolve({ ...target, repo: key })
    );
    expect(out.map((t) => t.repo)).toEqual(['mail']);
  });

  it('reports a policy refusal or config error instead of dropping the repo', async () => {
    const m = await load();
    await expect(
      m.selectAllTargets(listed, { all: 'hostinger' }, (key) =>
        key === 'other'
          ? Promise.reject(new Error('command refused by policy for other'))
          : Promise.resolve({ ...target, repo: key })
      )
    ).rejects.toThrow(/refused by policy/);
  });
});

describe('runDownload', () => {
  it('is incomplete before the first rsync call and complete only after an equal sha256', async () => {
    const m = await load();
    let during: string | undefined;
    const deps = baseDeps({
      runRsync: (req) => {
        during = readImageState(paths().state)?.status;
        writeFileSync(req.dest, 'image');
        return Promise.resolve({ exitCode: 0, literalBytes: 1, matchedBytes: 2 });
      },
    });
    const { exitCode, results } = await m.runDownload(opts(), deps);
    expect(during).toBe('incomplete');
    expect(exitCode).toBe(0);
    expect(results[0]?.status).toBe('complete');
    const st = readImageState(paths().state);
    expect(st?.status).toBe('complete');
    expect(st?.complete?.sha256).toBe(DIGEST);
    expect(st?.complete?.verify).toBe('sha256+rsync');
    expect(calls.at(-1)).toBe('quit');
  });

  it('a sha256 mismatch leaves the state incomplete and fails the run', async () => {
    const m = await load();
    const deps = baseDeps({ hashFile: async () => 'ee'.repeat(32) });
    const { exitCode, results } = await m.runDownload(opts(), deps);
    expect(exitCode).toBe(1);
    expect(results[0]?.status).not.toBe('complete');
    const st = readImageState(paths().state);
    expect(st?.status).toBe('incomplete');
    expect(st?.run.lastError).toMatch(/sha256 mismatch/);
  });

  it('--skip-verify records rsync verification only', async () => {
    const m = await load();
    const { results } = await m.runDownload(opts({ skipVerify: true }), baseDeps());
    expect(results[0]?.verify).toBe('rsync');
    expect(readImageState(paths().state)?.complete?.verify).toBe('rsync');
  });

  it('retries rsync exit 12 on the live session', async () => {
    const m = await load();
    let n = 0;
    const deps = baseDeps({
      runRsync: (req) => {
        n += 1;
        writeFileSync(req.dest, 'image');
        return Promise.resolve({ exitCode: n === 1 ? 12 : 0, literalBytes: 1, matchedBytes: 1 });
      },
    });
    const { exitCode } = await m.runDownload(opts(), deps);
    expect(exitCode).toBe(0);
    expect(n).toBe(2);
    expect(opened).toBe(1);
  });

  it('reopens the session on retry when it no longer answers ping', async () => {
    const m = await load();
    let n = 0;
    const deps = baseDeps({
      openSession: () => {
        opened += 1;
        return Promise.resolve(fakeSession({ pingOk: opened > 1 }));
      },
      runRsync: (req) => {
        n += 1;
        writeFileSync(req.dest, 'image');
        return Promise.resolve({ exitCode: n === 1 ? 255 : 0, literalBytes: 1, matchedBytes: 1 });
      },
    });
    const { exitCode } = await m.runDownload(opts(), deps);
    expect(exitCode).toBe(0);
    expect(opened).toBe(2);
  });

  it('fails at once on an exit code outside the retry set', async () => {
    const m = await load();
    let n = 0;
    const deps = baseDeps({
      runRsync: () => {
        n += 1;
        return Promise.resolve({ exitCode: 23, literalBytes: 0, matchedBytes: 0 });
      },
    });
    const { exitCode } = await m.runDownload(opts(), deps);
    expect(exitCode).toBe(1);
    expect(n).toBe(1);
    expect(readImageState(paths().state)?.status).toBe('incomplete');
  });

  it('Ctrl-C sends quit and exits 130 with the state written', async () => {
    const m = await load();
    const ac = new AbortController();
    const deps = baseDeps({
      signal: ac.signal,
      runRsync: () => {
        ac.abort();
        return Promise.resolve({ exitCode: 20, literalBytes: 0, matchedBytes: 0 });
      },
    });
    const { exitCode } = await m.runDownload(opts(), deps);
    expect(exitCode).toBe(130);
    expect(quits).toBe(1);
    const st = readImageState(paths().state);
    expect(st?.status).toBe('incomplete');
    expect(st?.history.at(-1)?.outcome).toBe('interrupted');
  });

  it('refuses with no session when rsync is missing', async () => {
    const m = await load();
    const deps = baseDeps({
      assertRsyncCapable: () => Promise.reject(new Error('rsync not found. Please install rsync.')),
    });
    await expect(m.runDownload(opts(), deps)).rejects.toThrow(/rsync/);
    expect(opened).toBe(0);
    expect(calls).toEqual([]);
  });

  it('refuses a missing --to directory without creating it', async () => {
    const m = await load();
    const missing = join(to, 'unplugged-drive');
    await expect(m.runDownload(opts({ to: missing }), baseDeps())).rejects.toThrow();
    expect(existsSync(missing)).toBe(false);
    expect(opened).toBe(0);
  });

  it('-o json prints one parseable document on stdout', async () => {
    const m = await load();
    const deps = baseDeps();
    await m.runDownload(opts({ output: 'json' }), deps);
    expect(deps.out).toHaveLength(1);
    const doc = JSON.parse(deps.out[0] ?? '');
    expect(doc.results).toHaveLength(1);
    expect(doc.results[0]).toMatchObject({ repo: 'mail', tag: 'latest', status: 'complete' });
  });
});
