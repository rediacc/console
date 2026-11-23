/**
 * WB1 (agent/plans/PLAN-rmcp-writeback.md Design 4): a command the container
 * executor dispatches pushes its config change back to config storage.
 *
 * `repo delete` of a repo whose machine left the config is config-only: it
 * archives the entry. Dispatched through the real serve app in container mode,
 * that archive must reach the store as exactly one push, which proves the
 * removal of every committed key of the repo with a tombstone (the server
 * refuses a push that drops a key without one), and the next command of the
 * same session must see the pushed version without pulling again.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
}));

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-writeback-push-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import {
  bootContainerExecutor,
  type ContainerExecutor,
  createFakeConfigStore,
  fakeRenet,
} from './writeback-harness.js';

const SHOP_GUID = '11111111-1111-4111-8111-111111111111';

function storedConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000c1',
    version: 5,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: {
      machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
      repositories: {
        // Placed on a machine the config no longer has: its delete is config-only.
        shop: {
          grand: 'latest',
          placement: { machine: 'gone-host' },
          tags: { latest: { repositoryGuid: SHOP_GUID, credential: 'shop-credential' } },
        },
        keep: {
          grand: 'latest',
          placement: { machine: 'm1' },
          tags: {
            latest: {
              repositoryGuid: '22222222-2222-4222-8222-222222222222',
              credential: 'keep-credential',
            },
          },
        },
      },
    },
    state: {},
    // The executor refuses destructive and grand-repo commands unless the org's policy allows them.
    policy: { version: 1, defaults: { commands: { allow: ['*'] }, allowGrandRepos: true } },
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

describe('WB1: a dispatched write is pushed back to config storage', () => {
  let executor: ContainerExecutor | undefined;

  afterEach(async () => {
    await executor?.close();
    executor = undefined;
  });

  it('one dispatched delete is one PUT with tombstones, and the next dispatch reads the pushed version', async () => {
    const store = await createFakeConfigStore(storedConfig());
    const renet = fakeRenet();
    executor = await bootContainerExecutor(store, renet.executor);
    await executor.grantKey();

    const deleted = await executor.command('repo delete', { yes: true }, { ref: 'shop' });

    expect(deleted.result.success).toBe(true);
    // Config-only: the machine is gone, so renet is never called.
    expect(renet.calls).toEqual([]);
    // The chain was minted writable.
    expect(store.mints.every((mint) => mint.write === true)).toBe(true);
    // Exactly one push, accepted, carrying tombstones for the removed repo's committed keys.
    expect(store.puts).toHaveLength(1);
    expect(store.puts[0]).toMatchObject({ version: 6, status: 200 });
    expect(store.puts[0]?.removedKeys.length).toBeGreaterThan(0);

    // What the store now holds: the repo archived with its GUID and credential, gone from the live map, the other repo untouched.
    const stored = await store.current();
    expect(store.version()).toBe(6);
    expect(Object.keys(stored.resources.repositories)).toEqual(['keep']);
    expect(stored.resources.deletedRepositories?.[0]).toMatchObject({
      repositoryGuid: SHOP_GUID,
      credential: 'shop-credential',
    });

    // The next dispatch of the same session reads the pushed version from the session's store, without pulling again: the deleted repo is not found.
    const pullsBefore = store.pulls;
    const again = await executor.command('repo delete', { yes: true }, { ref: 'shop' });
    expect(again.result.success).toBe(false);
    expect(`${again.stdout ?? ''}${again.stderr ?? ''}`).toMatch(/shop/);
    expect(store.pulls).toBe(pullsBefore);
    expect(store.puts).toHaveLength(1);
  });

  it('control: a read-only chain refuses the push, and the command fails with the store unchanged', async () => {
    const store = await createFakeConfigStore(storedConfig());
    const renet = fakeRenet();
    // The account server honours `write` only under a live grant; a chain minted read-only has its PUT refused.
    executor = await bootContainerExecutor(store, renet.executor);
    const realFetch = store.fetch;
    store.fetch = ((url: string | URL, init?: RequestInit) => {
      if (String(url).includes('/configs/executor-token') && init?.body) {
        const body = JSON.parse(init.body as string) as Record<string, unknown>;
        delete body.write;
        return realFetch(url, { ...init, body: JSON.stringify(body) });
      }
      return realFetch(url, init);
    }) as typeof fetch;
    await executor.close();
    executor = await bootContainerExecutor(store, renet.executor);
    await executor.grantKey();

    const deleted = await executor.command('repo delete', { yes: true }, { ref: 'shop' });

    expect(deleted.result.success).toBe(false);
    expect(deleted.result.errorCode).toBe('CONFIG_WRITE_FAILED');
    expect(store.version()).toBe(5);
    expect(
      Object.keys((await store.current()).resources.repositories).sort((x, y) => x.localeCompare(y))
    ).toEqual(['keep', 'shop']);
  });
});
