/**
 * WB2 (agent/plans/PLAN-rmcp-writeback.md Design 5): concurrent dispatched writes
 * of one session are serialized, and the container holds one token chain.
 *
 * Ten `repo delete` commands of one session run at once, each archiving a
 * different repo (one push each). The session's config store runs one
 * pull/session/PUT sequence at a time, each on the version the previous one
 * left, so the store ends ten versions on with every archive kept, no push ever
 * loses the compare-and-swap, and the chain is never presented a spent token.
 * The control runs the same ten edits through the store's write body without the
 * serialization: pushes built on the same version collide.
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
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-writeback-concurrency-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import { ConfigChain, SessionConfigStore } from '../config-writeback.js';
import {
  bootContainerExecutor,
  CONFIG_ID,
  type ContainerExecutor,
  createFakeConfigStore,
  EXECUTOR_TOKEN,
  type FakeConfigStore,
  fakeRenet,
  OWNER_TOKEN,
  STORE_ID,
} from './writeback-harness.js';

const NAMES = Array.from({ length: 10 }, (_, i) => `r${i}`);

function storedConfig(): RdcConfig {
  const repositories: Record<string, unknown> = {};
  NAMES.forEach((name, i) => {
    repositories[name] = {
      grand: 'latest',
      // Placed on a machine the config no longer has: each delete is config-only, one push.
      placement: { machine: 'gone-host' },
      tags: {
        latest: {
          repositoryGuid: `00000000-0000-4000-8000-${String(i).padStart(12, '0')}`,
          credential: `cred-${name}`,
        },
      },
    };
  });
  return {
    schemaVersion: 3,
    id: CONFIG_ID,
    version: 1,
    resources: { machines: {}, repositories },
    state: {},
    policy: { version: 1, defaults: { commands: { allow: ['*'] }, allowGrandRepos: true } },
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

/** The archive edit `repo delete` makes, for the control's direct writes. */
function archiveEdit(name: string) {
  return (config: RdcConfig): RdcConfig => {
    const repositories = { ...config.resources.repositories };
    delete repositories[name];
    return { ...config, resources: { ...config.resources, repositories } };
  };
}

/** A session store opened straight through the chain, as the loader opens one. */
async function openDirect(store: FakeConfigStore): Promise<SessionConfigStore> {
  const sessionId = 'session-direct';
  await store.fetch('https://account.test/account/api/v1/configs/executor-grant', {
    method: 'POST',
    headers: { authorization: `Bearer ${EXECUTOR_TOKEN}` },
    body: JSON.stringify({ sessionId, token: OWNER_TOKEN }),
  });
  const chain = new ConfigChain({
    accountUrl: 'https://account.test',
    executorToken: EXECUTOR_TOKEN,
    userId: 'user-owner',
    fetchImpl: store.fetch,
  });
  await chain.mint(sessionId);
  return SessionConfigStore.open({
    chain,
    sessionId,
    cek: store.cek,
    target: { storeId: STORE_ID, configId: CONFIG_ID, teamId: null },
  });
}

describe('WB2: one session writes one push at a time, on one chain', () => {
  let executor: ContainerExecutor | undefined;

  afterEach(async () => {
    await executor?.close();
    executor = undefined;
  });

  it('ten parallel dispatched writes make ten versions, no 409 and no spent token', async () => {
    const store = await createFakeConfigStore(storedConfig());
    executor = await bootContainerExecutor(store, fakeRenet().executor);
    await executor.grantKey();

    const results = await Promise.all(
      NAMES.map((name) => executor!.command('repo delete', { yes: true }, { ref: name }))
    );

    expect(results.map((r) => r.result.success)).toEqual(NAMES.map(() => true));
    expect(store.version()).toBe(1 + NAMES.length);
    expect(store.puts.map((put) => put.status)).toEqual(NAMES.map(() => 200));
    expect(store.exhausted).toBe(0);
    // One mint: the session's. No write needed a fresh chain.
    expect(store.mints).toHaveLength(1);
    const stored = await store.current();
    expect(stored.resources.repositories).toEqual({});
    expect(stored.resources.deletedRepositories).toHaveLength(NAMES.length);
  });

  it('control: the same ten writes without the serialization collide on the version', async () => {
    const store = await createFakeConfigStore(storedConfig());
    const session = await openDirect(store);

    // The write body the serialization wraps, called ten times at once.
    await Promise.allSettled(NAMES.map((name) => session.pushWithReplay(archiveEdit(name))));

    expect(store.puts.some((put) => put.status === 409)).toBe(true);
  });

  it('the serialized write of the same session store does not collide', async () => {
    const store = await createFakeConfigStore(storedConfig());
    const session = await openDirect(store);

    await Promise.all(NAMES.map((name) => session.write(archiveEdit(name))));

    expect(store.puts.map((put) => put.status)).toEqual(NAMES.map(() => 200));
    expect((await store.current()).resources.repositories).toEqual({});
  });
});
