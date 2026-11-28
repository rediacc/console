/**
 * The proxy session cache only saves a grant: a file that cannot be read or written costs the next
 * run a fresh grant and never fails the command that already ran (reviews 794b37a0.1, 794b37a0.2).
 */

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ProxySessionCache } from '../proxy-session-cache.js';

const URL_ = 'https://executor.test';
const TOKEN = 'rdt_owner';

describe('ProxySessionCache failure handling', () => {
  let scratch: string;

  beforeEach(() => {
    scratch = mkdtempSync(join(tmpdir(), 'rdc-session-cache-'));
  });
  afterEach(() => {
    rmSync(scratch, { recursive: true, force: true });
  });

  it('control: a writable dir stores and returns an entry', async () => {
    const cache = new ProxySessionCache({ dir: scratch });
    await cache.set(URL_, TOKEN, { mode: 'container', sessionId: 's1' });
    expect(await cache.get(URL_, TOKEN)).toMatchObject({ mode: 'container', sessionId: 's1' });
  });

  it('get answers undefined when the cache path is not a readable file', async () => {
    mkdirSync(join(scratch, 'proxy-sessions.json'));
    const cache = new ProxySessionCache({ dir: scratch });
    await expect(cache.get(URL_, TOKEN)).resolves.toBeUndefined();
  });

  it('set and delete resolve when the dir cannot be created or written', async () => {
    const blocker = join(scratch, 'blocker');
    writeFileSync(blocker, 'a file where the dir should be');
    const cache = new ProxySessionCache({ dir: join(blocker, 'tokens') });
    await expect(
      cache.set(URL_, TOKEN, { mode: 'container', sessionId: 's1' })
    ).resolves.toBeUndefined();
    await expect(cache.delete(URL_, TOKEN)).resolves.toBeUndefined();
    await expect(cache.get(URL_, TOKEN)).resolves.toBeUndefined();
  });
});
