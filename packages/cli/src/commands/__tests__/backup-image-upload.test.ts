/**
 * `rdc backup upload` against fakes: a recording import session and a fake rsync runner.
 *
 * Pins the API C1 implements in commands/backup-image.ts: `runUpload(options, deps)` takes every
 * side effect through `deps`, throws for a refusal, and returns `{ exitCode, results }`.
 * The local image and its state file are real files in a temp directory, written with the S1
 * state module. The module is loaded with a runtime path so these tests stay independent of the
 * command's import graph.
 */

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  beginRun,
  completeRun,
  type ImageState,
  localImagePaths,
  readImageState,
  recordUpload,
  writeImageState,
} from '../../services/backup-image/state.js';

interface ImportReady {
  staging: string;
  fresh: boolean;
  seeded: boolean;
  existingBytes: number;
  rsyncPath: string;
}
interface ImportSession {
  ready: ImportReady;
  finalize(sha256: string): Promise<{ path: string }>;
  quit(): Promise<void>;
}
interface ImportTarget {
  machine: string;
  guid: string;
  datastore: string;
  seedGuid?: string;
  allocatedBytes: number;
}
interface SourceRepo {
  name: string;
  tag: string;
  credential: string;
  grandGuid: string | null;
  guid: string;
}
interface UploadDeps {
  assertRsyncCapable(): Promise<void>;
  findRepoByGuid(guid: string): SourceRepo | undefined;
  findRepoByName(name: string): SourceRepo | undefined;
  mintGuid(): string;
  openImportSession(target: ImportTarget): Promise<ImportSession>;
  runRsync(req: { args: string[]; source: string; dest: string }): Promise<{
    exitCode: number;
    literalBytes: number;
    matchedBytes: number;
  }>;
  hashFile(path: string): Promise<string>;
  register(entry: {
    name: string;
    tag: string;
    guid: string;
    machine: string;
    lineage: string | null;
  }): Promise<void>;
  sleep(ms: number): Promise<void>;
  now(): Date;
  write(text: string): void;
  signal?: AbortSignal;
}
interface UploadOptions {
  image: string;
  to: string;
  as?: string;
  datastore?: string;
  fromRepo?: string;
  skipVerify?: boolean;
  config: string;
}
interface Module {
  runUpload(o: UploadOptions, d: UploadDeps): Promise<{ exitCode: number }>;
}

const load = (): Promise<Module> =>
  import(/* @vite-ignore */ fileURLToPath(new URL('../backup-image.ts', import.meta.url)));

const DIGEST = 'cd'.repeat(32);
const sourceRepo: SourceRepo = {
  name: 'mail',
  tag: 'latest',
  credential: 'secret',
  grandGuid: 'grand-1',
  guid: 'g-1',
};

let root: string;
let events: string[];
let rsyncArgs: string[][];
let registered: { name: string; tag: string }[];

function seedState(kind: 'complete' | 'incomplete', withUpload?: boolean, tag = 'latest'): string {
  const p = localImagePaths(root, 'hostinger', 'mail', tag);
  mkdirSync(p.machineDir, { recursive: true });
  writeFileSync(p.image, 'image');
  let st: ImageState = beginRun(null, {
    config: 'eu-remote',
    machine: 'hostinger',
    image: `mail.${tag}.img`,
    repo: { name: 'mail', tag, guid: 'g-1', grandGuid: 'grand-1' },
    snapshotTakenAt: '2026-10-29T10:00:00Z',
    snapshotName: '.snapshot-g-1-x',
    apparentBytes: 1024,
    allocatedBytes: 512,
    checkpoint: false,
    now: '2026-10-29T10:00:00Z',
  });
  if (kind === 'complete') {
    st = completeRun(st, {
      sha256: DIGEST,
      verify: 'sha256+rsync',
      literalBytes: 1,
      matchedBytes: 1,
      durationMs: 1,
      now: '2026-10-29T10:05:00Z',
    });
  }
  if (withUpload) {
    st = recordUpload(st, {
      machine: 'hostinger2',
      name: 'mail',
      guid: 'pending-guid',
      datastore: '/mnt/rediacc',
      startedAt: '2026-10-29T10:06:00Z',
      status: 'staging',
    });
  }
  writeImageState(p.state, st);
  return p.image;
}

function deps(over: Partial<UploadDeps> = {}, ready: Partial<ImportReady> = {}): UploadDeps {
  return {
    assertRsyncCapable: async () => undefined,
    findRepoByGuid: (g) => (g === 'g-1' ? sourceRepo : undefined),
    findRepoByName: () => undefined,
    mintGuid: () => 'fresh-guid',
    openImportSession: (t) => {
      events.push(`open:${t.guid}`);
      return Promise.resolve({
        ready: {
          staging: `/mnt/rediacc/repositories/.restore-${t.guid}`,
          fresh: true,
          seeded: false,
          existingBytes: 0,
          rsyncPath: '/usr/bin/rsync',
          ...ready,
        },
        finalize: (sha) => {
          events.push(`finalize:${sha}`);
          return Promise.resolve({ path: `/mnt/rediacc/repositories/${t.guid}` });
        },
        quit: () => {
          events.push('quit');
          return Promise.resolve();
        },
      });
    },
    runRsync: (req) => {
      events.push('rsync');
      rsyncArgs.push(req.args);
      return Promise.resolve({ exitCode: 0, literalBytes: 1, matchedBytes: 1 });
    },
    hashFile: async () => DIGEST,
    register: (e) => {
      registered.push({ name: e.name, tag: e.tag });
      events.push(`register:${e.guid}`);
      return Promise.resolve();
    },
    sleep: async () => undefined,
    now: () => new Date('2026-10-29T12:00:00Z'),
    write: () => undefined,
    ...over,
  };
}

const opts = (image: string, over: Partial<UploadOptions> = {}): UploadOptions => ({
  image,
  to: 'hostinger2',
  config: 'eu-remote',
  ...over,
});

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'ul-'));
  events = [];
  rsyncArgs = [];
  registered = [];
});
afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

describe('runUpload', () => {
  it('refuses an incomplete state as not usable', async () => {
    const m = await load();
    const image = seedState('incomplete');
    await expect(m.runUpload(opts(image), deps())).rejects.toThrow(/incomplete|not usable/i);
    expect(events).toEqual([]);
  });

  it('refuses a missing credential repo and names --from-repo', async () => {
    const m = await load();
    const image = seedState('complete');
    await expect(
      m.runUpload(opts(image), deps({ findRepoByGuid: () => undefined }))
    ).rejects.toThrow(/--from-repo/);
    expect(events).toEqual([]);
  });

  it('refuses a name already in the config and hints --as', async () => {
    const m = await load();
    const image = seedState('complete');
    await expect(
      m.runUpload(opts(image), deps({ findRepoByName: () => sourceRepo }))
    ).rejects.toThrow(/--as/);
  });

  it('registers only after the finalize, with the minted guid', async () => {
    const m = await load();
    const image = seedState('complete');
    const { exitCode } = await m.runUpload(opts(image), deps());
    expect(exitCode).toBe(0);
    const order = events.filter((e) => e !== 'quit');
    expect(order).toEqual([
      'open:fresh-guid',
      'rsync',
      `finalize:${DIGEST}`,
      'register:fresh-guid',
    ]);
    const st = readImageState(localImagePaths(root, 'hostinger', 'mail', 'latest').state);
    expect(st?.upload).toMatchObject({ guid: 'fresh-guid', status: 'finalized' });
  });

  it('registers a non-latest image under its own tag (9c3f5e10.1)', async () => {
    const m = await load();
    const image = seedState('complete', false, 'dev');
    const { exitCode } = await m.runUpload(opts(image), deps());
    expect(exitCode).toBe(0);
    expect(registered).toEqual([{ name: 'mail', tag: 'dev' }]);
  });

  it('Ctrl-C during the rsync quits the import session, skips finalize and register, keeps the pending record (9c3f5e10.5)', async () => {
    const m = await load();
    const image = seedState('complete');
    const ac = new AbortController();
    const d = deps({
      signal: ac.signal,
      runRsync: () => {
        events.push('rsync');
        ac.abort();
        return Promise.resolve({ exitCode: 20, literalBytes: 0, matchedBytes: 0 });
      },
    });
    const { exitCode } = await m.runUpload(opts(image), d);
    expect(exitCode).toBe(130);
    expect(events).toEqual(['open:fresh-guid', 'rsync', 'quit']);
    const st = readImageState(localImagePaths(root, 'hostinger', 'mail', 'latest').state);
    expect(st?.upload).toMatchObject({ guid: 'fresh-guid', status: 'staging' });
  });

  it('does not register when the finalize fails', async () => {
    const m = await load();
    const image = seedState('complete');
    const d = deps();
    const open = d.openImportSession;
    d.openImportSession = async (t) => {
      const s = await open(t);
      s.finalize = () => Promise.reject(new Error('sha256 mismatch on the machine'));
      return s;
    };
    await expect(m.runUpload(opts(image), d)).rejects.toThrow(/sha256 mismatch/);
    expect(events.some((e) => e.startsWith('register'))).toBe(false);
  });

  it('records the pending upload before any byte moves', async () => {
    const m = await load();
    const image = seedState('complete');
    const statePath = localImagePaths(root, 'hostinger', 'mail', 'latest').state;
    let atRsync: ImageState | null = null;
    const d = deps({
      runRsync: () => {
        atRsync = readImageState(statePath);
        return Promise.resolve({ exitCode: 0, literalBytes: 0, matchedBytes: 0 });
      },
    });
    await m.runUpload(opts(image), d);
    expect((atRsync as ImageState | null)?.upload).toMatchObject({
      guid: 'fresh-guid',
      status: 'staging',
    });
  });

  it('a resume reuses the pending guid', async () => {
    const m = await load();
    const image = seedState('complete', true);
    await m.runUpload(opts(image), deps());
    expect(events[0]).toBe('open:pending-guid');
    expect(events).toContain('register:pending-guid');
  });

  it('sends --sparse only when the staging is fresh', async () => {
    const m = await load();
    const image = seedState('complete');
    await m.runUpload(opts(image), deps({}, { fresh: true }));
    expect(rsyncArgs[0]).toContain('--sparse');
    rsyncArgs = [];
    const image2 = seedState('complete');
    await m.runUpload(opts(image2, { as: 'mail2' }), deps({}, { fresh: false, existingBytes: 10 }));
    expect(rsyncArgs[0]).not.toContain('--sparse');
  });
});
