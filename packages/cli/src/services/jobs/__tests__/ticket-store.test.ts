import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { COMPACT_THRESHOLD, foldEvents, TicketStore } from '../ticket-store.js';

let base: string;

beforeEach(() => {
  base = mkdtempSync(join(tmpdir(), 'rdc-tickets-'));
});
afterEach(() => {
  rmSync(base, { recursive: true, force: true });
});

const storeIn = (config = 'rediacc') => new TicketStore(config, base);

describe('ticket store: append and modes', () => {
  it('creates the directory 0700 and the file 0600', () => {
    const store = storeIn();
    store.append('starting', 'r1', { machine: 'm1', verb: 'repo up' });
    expect(statSync(store.dir).mode & 0o777).toBe(0o700);
    expect(statSync(store.path).mode & 0o777).toBe(0o600);
  });

  it('keeps the file at 0600 after later appends', () => {
    const store = storeIn();
    store.append('starting', 'r1');
    store.append('started', 'r1', { jobId: 'j1-aaaaaaaa' });
    expect(statSync(store.path).mode & 0o777).toBe(0o600);
  });

  it('never writes a secret field, even when one is passed', () => {
    const store = storeIn();
    store.append('starting', 'r1', {
      machine: 'm1',
      vault: { password: 'hunter2-vault' },
      env: { TOKEN: 'hunter2-env' },
      payload: 'hunter2-payload',
      via: { kind: 'proxy', url: 'https://user:hunter2-url@proxy.example/v1?token=hunter2-q' },
      then: { function: 'repository_up', params: { repo: 'web', password: 'hunter2-then' } },
    } as never);
    const raw = readFileSync(store.path, 'utf8');
    expect(raw).not.toContain('hunter2');
    expect(raw).toContain('"machine":"m1"');
    expect(raw).toContain('https://proxy.example/v1');
    expect(raw).toContain('"repo":"web"');
  });

  it('rejects a config name that would leave the jobs directory', () => {
    expect(() => new TicketStore('../evil', base)).toThrow();
  });

  it('concurrent processes appending lose no ticket', async () => {
    const script = join(base, 'append.mjs');
    writeFileSync(
      script,
      `import { TicketStore } from ${JSON.stringify(new URL('../ticket-store.ts', import.meta.url).href)};
const [,, base, tag] = process.argv;
const store = new TicketStore('rediacc', base);
for (let i = 0; i < 40; i++) store.append('starting', tag + '-' + i, { machine: 'm' });
`
    );
    const tsxLoader = pathToFileURL(createRequire(import.meta.url).resolve('tsx/esm')).href;
    // Three real processes, started back to back against the same file.
    const procs = ['a', 'b', 'c'].map(
      (tag) =>
        new Promise<number | null>((resolve) => {
          const child = spawn(process.execPath, ['--import', tsxLoader, script, base, tag], {
            stdio: 'inherit',
          });
          child.on('error', () => resolve(-1));
          child.on('exit', resolve);
        })
    );
    const codes = await Promise.all(procs);
    expect(codes).toEqual([0, 0, 0]);
    expect(storeIn().tickets()).toHaveLength(120);
  }, 90_000);
});

describe('ticket store: fold', () => {
  it('folds events by request id into one ticket', () => {
    const store = storeIn();
    store.append('starting', 'r1', {
      machine: 'm1',
      verb: 'repo up',
      repo: 'web',
      startedAt: '2026-01-01T00:00:00Z',
    });
    store.append('started', 'r1', { jobId: 'j1-aaaaaaaa', via: { kind: 'ssh' } });
    store.append('seen', 'r1', { lastSeenLine: 7 });
    store.append('seen', 'r1', { lastSeenLine: 3 });
    store.append('starting', 'r2', { machine: 'm2' });
    const [t1, t2] = storeIn().tickets();
    expect(t1).toMatchObject({
      requestId: 'r1',
      jobId: 'j1-aaaaaaaa',
      machine: 'm1',
      repo: 'web',
      state: 'running',
      lastSeenLine: 7,
      acknowledged: false,
    });
    expect(t2).toMatchObject({ requestId: 'r2', state: 'starting' });
    expect(t2.jobId).toBeUndefined();
  });

  it('a finished ticket stays finished and acknowledgement removes it from pending', () => {
    const store = storeIn();
    store.append('starting', 'r1', { machine: 'm1' });
    store.append('started', 'r1', { jobId: 'j1-aaaaaaaa' });
    store.append('finished', 'r1', { state: 'failed', exitCode: 3 });
    store.append('seen', 'r1', { state: 'running' });
    expect(store.tickets()[0]).toMatchObject({ state: 'failed', exitCode: 3 });
    expect(store.pending()).toHaveLength(1);
    store.append('acknowledged', 'r1');
    expect(store.pending()).toHaveLength(0);
  });

  it('mirrors steps and step-done, and ignores torn lines', () => {
    const store = storeIn();
    store.append('starting', 'r1', {
      steps: [{ name: 'postRepoUpTasks', on: 'success', params: { repo: 'web', token: 'x' } }],
    });
    store.append('step-done', 'r1', { step: 'postRepoUpTasks' });
    writeFileSync(store.path, '{"torn":', { flag: 'a' });
    const ticket = storeIn().tickets()[0];
    expect(ticket.steps).toEqual([
      { name: 'postRepoUpTasks', on: 'success', params: { repo: 'web' } },
    ]);
    expect(ticket.stepsDone).toEqual(['postRepoUpTasks']);
  });

  it('foldEvents keeps first-seen order', () => {
    const events = ['b', 'a', 'b'].map((id) => ({
      v: 1,
      ts: 't',
      kind: 'seen' as const,
      requestId: id,
    }));
    expect(foldEvents(events).map((t) => t.requestId)).toEqual(['b', 'a']);
  });
});

describe('ticket store: compaction', () => {
  function seed(store: TicketStore, acked: number, live: number): void {
    for (let i = 0; i < acked + live; i++) {
      store.append('starting', `r${i}`, { machine: 'm' });
      store.append('started', `r${i}`, { jobId: `j${i}-aaaaaaaa` });
      if (i < acked) store.append('acknowledged', `r${i}`);
    }
  }

  it('does nothing at or under the threshold', () => {
    const store = storeIn();
    seed(store, COMPACT_THRESHOLD, 2);
    const before = readFileSync(store.path, 'utf8');
    expect(store.compactIfNeeded()).toBe(false);
    expect(readFileSync(store.path, 'utf8')).toBe(before);
  });

  it('drops acknowledged tickets past the threshold and keeps the live ones', () => {
    const store = storeIn();
    seed(store, COMPACT_THRESHOLD + 1, 3);
    expect(store.compactIfNeeded()).toBe(true);
    const tickets = storeIn().tickets();
    expect(tickets).toHaveLength(3);
    expect(tickets.every((t) => !t.acknowledged)).toBe(true);
    expect(statSync(store.path).mode & 0o777).toBe(0o600);
    // appends after compaction still land
    store.append('starting', 'after', { machine: 'm' });
    expect(storeIn().tickets()).toHaveLength(4);
  });

  it('leaves no lock file behind', () => {
    const store = storeIn();
    seed(store, COMPACT_THRESHOLD + 1, 1);
    store.compactIfNeeded();
    expect(() => statSync(`${store.path}.lock`)).toThrow();
  });
});
