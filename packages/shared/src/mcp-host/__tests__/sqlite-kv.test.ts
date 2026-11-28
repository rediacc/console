import { DatabaseSync } from 'node:sqlite';
import { describe, expect, it } from 'vitest';
import { SqliteKvNamespace } from '../sqlite-kv.js';

function namespace(start = 1_800_000_000_000) {
  let now = start;
  const kv = new SqliteKvNamespace(new DatabaseSync(':memory:'), {
    now: () => now,
  });
  return {
    kv,
    advance(seconds: number) {
      now += seconds * 1000;
    },
  };
}

describe('SqliteKvNamespace', () => {
  it('reads back text and JSON, overwrites, and deletes', async () => {
    const { kv } = namespace();
    await kv.put('a', '{"n":1}');
    expect(await kv.get('a')).toBe('{"n":1}');
    expect(await kv.get('a', { type: 'json' })).toEqual({ n: 1 });
    expect(await kv.get('a', 'json')).toEqual({ n: 1 });
    await kv.put('a', '{"n":2}');
    expect(await kv.get('a', { type: 'json' })).toEqual({ n: 2 });
    await kv.delete('a');
    expect(await kv.get('a')).toBeNull();
  });

  it('expires a key after expirationTtl and hides it from list', async () => {
    const { kv, advance } = namespace();
    await kv.put('t', 'v', { expirationTtl: 60 });
    advance(59);
    expect(await kv.get('t')).toBe('v');
    expect((await kv.list()).keys.map((k) => k.name)).toEqual(['t']);
    advance(1);
    expect(await kv.get('t')).toBeNull();
    expect((await kv.list()).keys).toEqual([]);
  });

  it('honours an absolute expiration and reports it in list', async () => {
    const { kv, advance } = namespace(1_800_000_000_000);
    await kv.put('e', 'v', { expiration: 1_800_000_120 });
    expect((await kv.list()).keys).toEqual([{ name: 'e', expiration: 1_800_000_120 }]);
    advance(120);
    expect(await kv.get('e')).toBeNull();
  });

  it('refuses a TTL below the Workers KV floor of 60 seconds', async () => {
    const { kv } = namespace();
    await expect(kv.put('x', 'v', { expirationTtl: 59 })).rejects.toThrow(RangeError);
    await expect(kv.put('x', 'v', { expiration: 1_800_000_030 })).rejects.toThrow(RangeError);
    expect(await kv.get('x')).toBeNull();
  });

  it('lists by prefix in key order and pages with a cursor', async () => {
    const { kv } = namespace();
    for (const key of ['grant:u:3', 'grant:u:1', 'token:u:1', 'grant:u:2', 'grantx']) {
      await kv.put(key, '1');
    }
    const first = await kv.list({ prefix: 'grant:', limit: 2 });
    expect(first.keys.map((k) => k.name)).toEqual(['grant:u:1', 'grant:u:2']);
    expect(first.list_complete).toBe(false);
    if (first.list_complete) throw new Error('unreachable');
    const second = await kv.list({
      prefix: 'grant:',
      limit: 2,
      cursor: first.cursor,
    });
    expect(second.keys.map((k) => k.name)).toEqual(['grant:u:3']);
    expect(second.list_complete).toBe(true);
  });

  it('treats LIKE wildcards in a prefix literally', async () => {
    const { kv } = namespace();
    await kv.put('a_b', '1');
    await kv.put('axb', '1');
    await kv.put('a%c', '1');
    expect((await kv.list({ prefix: 'a_' })).keys.map((k) => k.name)).toEqual(['a_b']);
    expect((await kv.list({ prefix: 'a%' })).keys.map((k) => k.name)).toEqual(['a%c']);
  });

  it('lists by a prefix with non-BMP characters', async () => {
    const { kv } = namespace();
    const prefix = 'grant:\u{1F600}:';
    await kv.put(`${prefix}1`, '1');
    await kv.put(`${prefix}2`, '1');
    await kv.put('grant:other:1', '1');
    expect((await kv.list({ prefix })).keys.map((k) => k.name)).toEqual([
      `${prefix}1`,
      `${prefix}2`,
    ]);
  });

  it('answers a get of malformed JSON with a rejected promise, not a throw', async () => {
    const { kv } = namespace();
    await kv.put('bad', '{not json');
    let pending: Promise<unknown> | undefined;
    expect(() => {
      pending = kv.get('bad', 'json');
    }).not.toThrow();
    await expect(pending).rejects.toThrow(SyntaxError);
  });
});
