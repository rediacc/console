/**
 * WB3 (agent/plans/PLAN-rmcp-writeback.md Design 4, 5): the compare-and-swap and
 * token-chain failure paths of a dispatched write.
 *
 * A push that loses the compare-and-swap to another device pulls the store's
 * copy and applies its edit again, so both edits survive; one that keeps losing
 * fails with CONFIG_CONFLICT after its replays. A token the store calls spent is
 * replaced by one fresh mint; a second refusal fails the write, and because the
 * write precedes the host job, the machine is never called.
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
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-writeback-conflict-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import { MAX_CONFLICT_REPLAYS } from '../config-writeback.js';
import {
  bootContainerExecutor,
  type ContainerExecutor,
  createFakeConfigStore,
  fakeRenet,
} from './writeback-harness.js';

function storedConfig(): RdcConfig {
  const repo = (i: number, machine: string) => ({
    grand: 'latest',
    placement: { machine },
    tags: {
      latest: {
        repositoryGuid: `00000000-0000-4000-8000-00000000000${i}`,
        credential: `cred-${i}`,
      },
    },
  });
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000c3',
    version: 2,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: {
      machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
      // Placed on a machine the config no longer has: their deletes are config-only.
      repositories: { a: repo(1, 'gone-host'), b: repo(2, 'gone-host') },
    },
    state: {},
    policy: { version: 1, defaults: { commands: { allow: ['*'] }, allowGrandRepos: true } },
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

/** Another device adding machine `name`. */
function addMachine(name: string) {
  return (config: RdcConfig): RdcConfig => ({
    ...config,
    resources: {
      ...config.resources,
      machines: {
        ...config.resources.machines,
        [name]: { ip: '10.9.9.9', user: 'root', port: 22 },
      },
    },
  });
}

describe('WB3: conflict replay and chain exhaustion', () => {
  let executor: ContainerExecutor | undefined;

  afterEach(async () => {
    await executor?.close();
    executor = undefined;
  });

  it('a concurrent external push forces a replay, and both edits survive', async () => {
    const store = await createFakeConfigStore(storedConfig());
    executor = await bootContainerExecutor(store, fakeRenet().executor);
    await executor.grantKey();
    let raced = false;
    store.beforePut = async () => {
      if (raced) return;
      raced = true;
      await store.externalPush(addMachine('laptop-added'));
    };

    const deleted = await executor.command('repo delete', { yes: true }, { ref: 'a' });

    expect(deleted.result.success).toBe(true);
    expect(store.puts.map((put) => put.status)).toEqual([409, 200]);
    const stored = await store.current();
    // The other device's machine and this command's archive are both in the store.
    expect(Object.keys(stored.resources.machines).sort((x, y) => x.localeCompare(y))).toEqual([
      'laptop-added',
      'm1',
    ]);
    expect(Object.keys(stored.resources.repositories)).toEqual(['b']);
    expect(stored.resources.deletedRepositories?.[0]?.repositoryGuid).toBe(
      '00000000-0000-4000-8000-000000000001'
    );
  });

  it('a conflict on every replay surfaces CONFIG_CONFLICT', async () => {
    const store = await createFakeConfigStore(storedConfig());
    executor = await bootContainerExecutor(store, fakeRenet().executor);
    await executor.grantKey();
    let racer = 0;
    store.beforePut = async () => {
      racer += 1;
      await store.externalPush(addMachine(`other-${racer}`));
    };

    const deleted = await executor.command('repo delete', { yes: true }, { ref: 'a' });

    expect(deleted.result.success).toBe(false);
    expect(deleted.result.errorCode).toBe('CONFIG_CONFLICT');
    // The first push and its three replays all lost; no fifth push went out.
    expect(store.puts.map((put) => put.status)).toEqual(
      Array.from({ length: MAX_CONFLICT_REPLAYS + 1 }, () => 409)
    );
    expect(
      Object.keys((await store.current()).resources.repositories).sort((x, y) => x.localeCompare(y))
    ).toEqual(['a', 'b']);
  });

  it('a token at its third use is replaced by one fresh mint', async () => {
    const store = await createFakeConfigStore(storedConfig());
    // No rotation: the executor keeps presenting one token until the store calls it spent.
    store.rotate = false;
    executor = await bootContainerExecutor(store, fakeRenet().executor);
    await executor.grantKey();

    // The pull, `/session` and the PUT are the token's three uses.
    const first = await executor.command('repo delete', { yes: true }, { ref: 'a' });
    expect(first.result.success).toBe(true);
    expect(store.mints).toHaveLength(1);

    // The next `/session` meets the spent token: one re-mint, and the write goes through.
    const second = await executor.command('repo delete', { yes: true }, { ref: 'b' });
    expect(second.result.success).toBe(true);
    expect(store.exhausted).toBe(1);
    expect(store.mints).toHaveLength(2);
    expect(store.mints.every((mint) => mint.write === true)).toBe(true);
    expect((await store.current()).resources.repositories).toEqual({});
  });

  it('a second exhaustion fails the command before any host call', async () => {
    const store = await createFakeConfigStore(storedConfig());
    store.rotate = false;
    const renet = fakeRenet();
    executor = await bootContainerExecutor(store, renet.executor);
    await executor.grantKey();
    const first = await executor.command('repo delete', { yes: true }, { ref: 'a' });
    expect(first.result.success).toBe(true);

    // From here every minted token is born spent: the re-mint cannot cure the refusal.
    store.mintSpent = true;
    // The warm session's version check (PLAN-rmcp-executor-hardening Design 5) is the chain's first request now, so the spent chain is met there and the command is refused before it is dispatched.
    await expect(
      executor.command('repo create', { machine: 'm1', size: '1G' }, { name: 'fresh' })
    ).rejects.toThrow(/could not check the config version.*token_exhausted/);
    expect(renet.calls).toEqual([]);
    // The spent session token, then the spent re-mint: two refusals, one re-mint, no third try.
    expect(store.exhausted).toBe(2);
    expect(store.mints).toHaveLength(2);
    expect(Object.keys((await store.current()).resources.repositories)).toEqual(['b']);
  });
});
