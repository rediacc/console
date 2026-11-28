/**
 * RW-KV: one suite, two KV implementations. The SQLite adapter the Node host hands the OAuth
 * library and Miniflare's real Workers KV answer the same calls the same way, so a difference
 * between the hosts shows up here rather than in the OAuth flow. TTL expiry needs the clock:
 * the SQLite adapter takes an injected one, and Miniflare KV runs on real time, so expiry is
 * proved against the adapter only and the control checks what both report (the expiry stamp
 * and the refusal below 60 seconds).
 */

import { DatabaseSync } from 'node:sqlite';
import { convertV4MiniflareOptions, Miniflare } from 'miniflare';
import { afterAll, describe, expect, it } from 'vitest';
import { SqliteKvNamespace } from '../sqlite-kv.js';

interface KvLike {
  get(key: string, options?: unknown): Promise<unknown>;
  put(key: string, value: string, options?: Record<string, number>): Promise<void>;
  delete(key: string): Promise<void>;
  list(options?: { prefix?: string; cursor?: string; limit?: number }): Promise<{
    keys: { name: string; expiration?: number }[];
    list_complete: boolean;
    cursor?: string;
  }>;
}

interface Subject {
  kv: KvLike;
  advance?: (seconds: number) => void;
}

const miniflares: Miniflare[] = [];

const hosts: Record<string, () => Promise<Subject>> = {
  sqlite: () => {
    let now = Date.now();
    const kv = new SqliteKvNamespace(new DatabaseSync(':memory:'), { now: () => now });
    return Promise.resolve({
      kv: kv as unknown as KvLike,
      advance(seconds) {
        now += seconds * 1000;
      },
    });
  },
  miniflare: async () => {
    const mf = new Miniflare(
      convertV4MiniflareOptions({
        modules: [
          {
            type: 'ESModule',
            path: 'worker.mjs',
            contents: 'export default { fetch() { return new Response("ok"); } };',
          },
        ],
        compatibilityDate: '2026-11-01',
        kvNamespaces: ['KV'],
      })
    );
    await mf.ready;
    miniflares.push(mf);
    return { kv: (await mf.getKVNamespace('KV')) as unknown as KvLike };
  },
};

afterAll(async () => {
  await Promise.all(miniflares.map((mf) => mf.dispose()));
});

describe.each(Object.keys(hosts))('KV semantics on %s', (host) => {
  const subject = () => hosts[host]!();

  it('overwrites a key and reads text and JSON', async () => {
    const { kv } = await subject();
    await kv.put('a', '{"n":1}');
    expect(await kv.get('a')).toBe('{"n":1}');
    expect(await kv.get('a', { type: 'json' })).toEqual({ n: 1 });
    await kv.put('a', '{"n":2}');
    expect(await kv.get('a', 'json')).toEqual({ n: 2 });
    expect(await kv.get('missing')).toBeNull();
  });

  it('deletes a key and tolerates deleting a missing one', async () => {
    const { kv } = await subject();
    await kv.put('d', '1');
    await kv.delete('d');
    await kv.delete('d');
    expect(await kv.get('d')).toBeNull();
  });

  it('lists by prefix in key order and pages with a cursor', async () => {
    const { kv } = await subject();
    for (const key of ['grant:u:3', 'grant:u:1', 'token:u:1', 'grant:u:2', 'grantx']) {
      await kv.put(key, '1');
    }
    const names: string[] = [];
    let cursor: string | undefined;
    let pages = 0;
    for (;;) {
      const page = await kv.list({ prefix: 'grant:', limit: 2, ...(cursor ? { cursor } : {}) });
      names.push(...page.keys.map((k) => k.name));
      pages += 1;
      if (page.list_complete) break;
      cursor = page.cursor;
    }
    expect(names).toEqual(['grant:u:1', 'grant:u:2', 'grant:u:3']);
    expect(pages).toBe(2);
  });

  it('reports the absolute expiry of a TTL key in list', async () => {
    const { kv } = await subject();
    const before = Math.floor(Date.now() / 1000);
    await kv.put('t', 'v', { expirationTtl: 120 });
    const [entry] = (await kv.list({ prefix: 't' })).keys;
    expect(entry?.name).toBe('t');
    expect(entry?.expiration).toBeGreaterThanOrEqual(before + 120);
    expect(entry?.expiration).toBeLessThanOrEqual(before + 125);
  });

  it('refuses a TTL below 60 seconds', async () => {
    const { kv } = await subject();
    await expect(kv.put('x', 'v', { expirationTtl: 59 })).rejects.toThrow();
    expect(await kv.get('x')).toBeNull();
  });

  it('expires a TTL key once the clock passes it', async (context) => {
    const { kv, advance } = await subject();
    if (!advance) {
      context.skip();
      return;
    }
    await kv.put('e', 'v', { expirationTtl: 60 });
    advance(59);
    expect(await kv.get('e')).toBe('v');
    advance(1);
    expect(await kv.get('e')).toBeNull();
    expect((await kv.list()).keys).toEqual([]);
  });
});
