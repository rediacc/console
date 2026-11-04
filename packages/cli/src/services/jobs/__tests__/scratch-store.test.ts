import { mkdirSync, mkdtempSync, rmSync, statSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ScratchStore } from '../scratch-store.js';

let dir: string;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'scratch-store-'));
});

afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

describe('ScratchStore', () => {
  it('reads back what each key wrote, last write winning, and drops the group', () => {
    const store = new ScratchStore('c1', dir);
    store.write('g1', 'm1', { ok: true, value: '{"a":1}' });
    store.write('g1', 'm2', { ok: false, error: 'boom' });
    store.write('g1', 'm1', { ok: true, value: '{"a":2}' });
    expect(store.read('g1')).toEqual(
      new Map([
        ['m1', { ok: true, value: '{"a":2}' }],
        ['m2', { ok: false, error: 'boom' }],
      ])
    );
    store.drop('g1');
    expect(store.read('g1').size).toBe(0);
  });

  it('keeps groups apart and encodes a key that would leave the directory', () => {
    const store = new ScratchStore('c1', dir);
    store.write('g1', '../escape', { ok: true, value: 'x' });
    store.write('g2', 'm1', { ok: true, value: 'y' });
    expect([...store.read('g1').keys()]).toEqual(['../escape']);
    expect([...store.read('g2').keys()]).toEqual(['m1']);
    expect(() => store.write('../g', 'm', { ok: true, value: '' })).toThrow(
      /Invalid scratch group/
    );
  });

  it('writes private files and skips a torn record', () => {
    const store = new ScratchStore('c1', dir);
    store.write('g1', 'm1', { ok: true, value: 'x' });
    const group = join(dir, 'jobs', 'c1.scratch', 'g1');
    expect(statSync(group).mode & 0o777).toBe(0o700);
    writeFileSync(join(group, 'torn.json'), '{"key":"t","ok":tr');
    expect([...store.read('g1').keys()]).toEqual(['m1']);
  });

  it('removes a group untouched for a day on the next write, and only that one', () => {
    const store = new ScratchStore('c1', dir);
    store.write('old', 'm1', { ok: true, value: 'x' });
    store.write('fresh', 'm1', { ok: true, value: 'y' });
    const old = join(dir, 'jobs', 'c1.scratch', 'old');
    const past = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000);
    utimesSync(old, past, past);
    mkdirSync(join(dir, 'jobs', 'c1.scratch', 'other'), { recursive: true });
    store.write('new', 'm1', { ok: true, value: 'z' });
    expect(store.read('old').size).toBe(0);
    expect(store.read('fresh').size).toBe(1);
  });

  it('reports the group complete only when every key finished, and claims it once', () => {
    const store = new ScratchStore('cfg', dir);
    expect(store.allFinished('g1', [])).toBe(true);
    store.finish('g1', 'm1');
    expect(store.allFinished('g1', ['m1', 'm2'])).toBe(false);
    store.finish('g1', 'm2');
    expect(store.allFinished('g1', ['m1', 'm2'])).toBe(true);
    expect(store.claim('g1')).toBe(true);
    expect(store.claim('g1')).toBe(false);
    expect(store.read('g1').size).toBe(0);
  });
});
