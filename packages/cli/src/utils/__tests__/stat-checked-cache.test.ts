import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { StatCheckedCache } from '../stat-checked-cache.js';

describe('StatCheckedCache', () => {
  let dir: string;
  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'stat-cache-'));
  });
  afterEach(() => fs.rmSync(dir, { recursive: true, force: true }));

  it('returns a stored path while its file is unchanged', () => {
    const file = path.join(dir, 'bin');
    fs.writeFileSync(file, 'one');
    const cache = new StatCheckedCache();
    cache.set('k', file);
    expect(cache.get('k')).toBe(file);
    expect(cache.get('other')).toBeUndefined();
  });

  it('drops an entry whose file was removed', () => {
    const file = path.join(dir, 'bin');
    fs.writeFileSync(file, 'one');
    const cache = new StatCheckedCache();
    cache.set('k', file);
    fs.rmSync(file);
    expect(cache.get('k')).toBeUndefined();
    fs.writeFileSync(file, 'one');
    expect(cache.get('k')).toBeUndefined();
  });

  it('drops an entry whose file changed size', () => {
    const file = path.join(dir, 'bin');
    fs.writeFileSync(file, 'one');
    const cache = new StatCheckedCache();
    cache.set('k', file);
    fs.writeFileSync(file, 'a longer replacement');
    expect(cache.get('k')).toBeUndefined();
  });

  it('drops an entry whose mtime moved with the size unchanged', () => {
    const file = path.join(dir, 'bin');
    fs.writeFileSync(file, 'one');
    const cache = new StatCheckedCache();
    cache.set('k', file);
    const later = new Date(Date.now() + 60_000);
    fs.utimesSync(file, later, later);
    expect(cache.get('k')).toBeUndefined();
  });

  it('does not store a path that cannot be stat-ed', () => {
    const cache = new StatCheckedCache();
    cache.set('k', path.join(dir, 'missing'));
    fs.writeFileSync(path.join(dir, 'missing'), 'x');
    expect(cache.get('k')).toBeUndefined();
  });

  it('sees a file installed after a miss once the lookup is stored again', () => {
    const file = path.join(dir, 'late');
    const cache = new StatCheckedCache();
    cache.set('k', file);
    expect(cache.get('k')).toBeUndefined();
    fs.writeFileSync(file, 'installed');
    cache.set('k', file);
    expect(cache.get('k')).toBe(file);
  });

  it('a miss replaces the stored hit instead of leaving the old path served', () => {
    const file = path.join(dir, 'bin');
    fs.writeFileSync(file, 'one');
    const cache = new StatCheckedCache();
    cache.set('k', file);
    cache.set('k', path.join(dir, 'gone'));
    expect(cache.get('k')).toBeUndefined();
  });
});
