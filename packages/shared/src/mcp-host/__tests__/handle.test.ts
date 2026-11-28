/**
 * The `authRequest` handle store (oauth/handle.ts): a handle that does not verify resolves to nothing, whatever its shape, and never throws (review 32ad8b14.1).
 */
import { describe, expect, it } from 'vitest';
import { createAuthRequestStore, type HandleKv, type StoredAuthRequest } from '../oauth/handle.js';

function memoryKv(): HandleKv {
  const entries = new Map<string, string>();
  return {
    get: (key) => Promise.resolve(entries.get(key) ?? null),
    put: (key, value) => {
      entries.set(key, value);
      return Promise.resolve();
    },
    delete: (key) => {
      entries.delete(key);
      return Promise.resolve();
    },
  };
}

const STORED = { authRequest: { clientId: 'c1' } } as unknown as StoredAuthRequest;
const SECRET = 'handle-test-secret';

describe('createAuthRequestStore', () => {
  it('control: a handle it issued peeks, then takes once', async () => {
    const store = createAuthRequestStore(memoryKv(), SECRET);
    const handle = await store.put(STORED);
    expect(await store.peek(handle)).toEqual(STORED);
    expect(await store.take(handle)).toEqual(STORED);
    expect(await store.take(handle)).toBeNull();
  });

  it('answers null, never an error, for a MAC segment whose length is 1 mod 4', async () => {
    const store = createAuthRequestStore(memoryKv(), SECRET);
    const id = (await store.put(STORED)).split('.')[0] as string;
    for (const mac of ['A', 'AAAAA', 'AAAAAAAAA']) {
      expect(await store.peek(`${id}.${mac}`), mac).toBeNull();
      expect(await store.take(`${id}.${mac}`), mac).toBeNull();
    }
  });

  it('answers null for a forged MAC of a well-formed length and for malformed shapes', async () => {
    const store = createAuthRequestStore(memoryKv(), SECRET);
    const handle = await store.put(STORED);
    const [id] = handle.split('.') as [string];
    for (const bad of [`${id}.${'A'.repeat(43)}`, id, `${id}.`, '.x', `${id}.a+b`]) {
      expect(await store.peek(bad), bad).toBeNull();
    }
  });
});
