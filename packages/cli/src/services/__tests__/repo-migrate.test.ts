/**
 * migrate routing tests (design: derived-routing repair family, defect 1 / R1).
 *
 * The load-bearing assertion is RED-FIRST: after a successful `repo migrate
 * <name> --to <target>`, resolving the same ref must route to the TARGET. On the
 * pre-R1 code migrate never rewrote placement, so resolveMachine kept yielding
 * the SOURCE — the silent wrong-host redeploy bug, captured here in one assert.
 *
 * migrateRepo's collaborators are mocked (executor scripted green, config writes
 * tracked in-memory); the routing assertion runs the REAL resolveMachine over a
 * PlacementView built from the placement migrate wrote.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlacementView } from '../addressing/resolve-machine.js';
import { resolveMachine } from '../addressing/resolve-machine.js';

/** Shared, hoisted so the vi.mock factories can close over it. */
const h = vi.hoisted(() => ({
  GUID: '11111111-1111-4111-8111-111111111111',
  /** Placement migrate wrote via configService.setRepositoryPlacement, if any. */
  written: undefined as { machine: string } | undefined,
  /** renet function name -> whether execute() should report failure. */
  failOn: null as string | null,
  /** repository_delete calls captured (R3). */
  deletedRepos: [] as string[],
}));

vi.mock('../config/config-resources.js', () => ({
  configService: {
    // undefined config => the R2 family guard is skipped (the fixture family is
    // supplied to resolveMachine directly, not through this service).
    getCurrent: vi.fn().mockResolvedValue(undefined),
    getRepository: vi.fn().mockResolvedValue({ repositoryGuid: h.GUID }),
    getLocalConfig: vi.fn().mockResolvedValue({ machines: { m1: {}, m2: {} } }),
    ensureRepositoryNetworkId: vi.fn().mockResolvedValue(1),
    setRepositoryPlacement: vi.fn((_family: string, placement: { machine: string }) => {
      h.written = placement;
      return Promise.resolve();
    }),
  },
}));

vi.mock('../executor/executor-factory.js', () => ({
  getExecutor: () => ({
    execute: vi.fn((req: { functionName: string; params?: Record<string, unknown> }) => {
      if (req.functionName === 'repository_delete') {
        h.deletedRepos.push(String(req.params?.repository ?? ''));
      }
      if (h.failOn && req.functionName === h.failOn) {
        return Promise.resolve({ success: false, error: 'scripted failure' });
      }
      // repository_list (assertNotMountedOnTarget) needs parseable stdout.
      return Promise.resolve({ success: true, stdout: '[]' });
    }),
  }),
}));

vi.mock('../../utils/spinner.js', () => ({
  // Run the wrapped work; drop the spinner chrome.
  withSpinner: (_label: string, fn: () => Promise<unknown>) => fn(),
}));

vi.mock('../repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../commands/repo-backup.js', () => ({
  autoProvisionTarget: vi.fn().mockResolvedValue(undefined),
  buildPushParams: () => ({ params: {} }),
}));

vi.mock('../../commands/repo-batch-utils.js', () => ({
  postRepoUpTasks: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../utils/remote-resolve.js', () => ({
  resolveRemoteName: (name: string) => Promise.resolve({ type: 'machine', name }),
}));

vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: { REPO_PUSH: 'repo push' },
}));

vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: vi.fn().mockResolvedValue({ name: 'shop', repoKey: 'shop', machineName: 'm1' }),
}));

vi.mock('../core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { migrateRepo } from '../../commands/repo-migrate.js';
import { ValidationError } from '../../utils/errors.js';
import { resolveRepoRef } from '../../utils/repo-target.js';
import { configService } from '../config/config-resources.js';

/** Stand up a family record for the R2 guards (which read configService.getCurrent). */
function familyConfig(grand: string, tags: string[]): void {
  vi.mocked(configService.getCurrent).mockResolvedValue({
    resources: {
      repositories: {
        shop: {
          grand,
          tags: Object.fromEntries(tags.map((tg) => [tg, { repositoryGuid: h.GUID }])),
        },
      },
    },
  } as never);
}

/** Build a PlacementView whose sole family carries `placement`. */
function viewWith(placement: { machine: string }): PlacementView {
  return {
    families: {
      shop: { grand: 'main', tags: { main: { repositoryGuid: h.GUID } }, placement },
    },
    datastores: {},
    stateDatastores: {},
    machines: { m1: { ip: '10.0.0.1', user: 'root' }, m2: { ip: '10.0.0.2', user: 'root' } },
  };
}

beforeEach(() => {
  h.written = undefined;
  h.failOn = null;
  h.deletedRepos = [];
  // Re-establish defaults each test: clearAllMocks() wipes call history but NOT
  // implementations, so a per-test getCurrent/resolveRepoRef override would leak.
  vi.mocked(configService.getCurrent).mockResolvedValue(undefined);
  vi.mocked(resolveRepoRef).mockResolvedValue({
    name: 'shop',
    repoKey: 'shop',
    machineName: 'm1',
    tag: 'main',
  });
});

afterEach(() => vi.clearAllMocks());

describe('repo migrate — placement rewrite (R1)', () => {
  it('routes the ref to the TARGET machine after a successful migrate', async () => {
    await migrateRepo('shop', { to: 'm2' });

    // The declaration migrate left behind is what resolveMachine reads. Before
    // R1 nothing was written, so this falls back to the source and FAILS.
    const declared = h.written ?? { machine: 'm1' };
    const resolved = await resolveMachine('shop', viewWith(declared));
    expect(resolved.machine).toBe('m2');
  });

  it('leaves placement on the SOURCE when phase 1 fails (pre-cutover)', async () => {
    h.failOn = 'backup_push';
    await expect(migrateRepo('shop', { to: 'm2' })).rejects.toThrow();

    const declared = h.written ?? { machine: 'm1' };
    const resolved = await resolveMachine('shop', viewWith(declared));
    expect(resolved.machine).toBe('m1');
  });

  it('rewrites placement to the target BEFORE phase 3, so a phase-3 failure keeps it there', async () => {
    h.failOn = 'repository_up';
    await expect(migrateRepo('shop', { to: 'm2' })).rejects.toThrow();
    // The rewrite happened at end of phase 2, so recovery lands on the target.
    expect(h.written).toEqual({ machine: 'm2' });
  });
});

describe('repo migrate — family semantics (R2, fallback scope)', () => {
  it('exits 2 on a fork ref, teaching push/promote', async () => {
    familyConfig('main', ['main', 'test']);
    vi.mocked(resolveRepoRef).mockResolvedValueOnce({
      name: 'shop',
      repoKey: 'shop:test',
      machineName: 'm1',
      tag: 'test',
    });
    // ValidationError is the exit-2 refusal class (handleError -> exit 2), the
    // same precedent `repo promote` uses for its not-a-fork refusal.
    await expect(migrateRepo('shop:test', { to: 'm2' })).rejects.toBeInstanceOf(ValidationError);
    // Nothing moved: no placement write, no source delete.
    expect(h.written).toBeUndefined();
    expect(h.deletedRepos).toHaveLength(0);
  });

  it('refuses a family that has forks (bare grand ref), exit 2', async () => {
    familyConfig('main', ['main', 'test']);
    await expect(migrateRepo('shop', { to: 'm2' })).rejects.toBeInstanceOf(ValidationError);
    expect(h.written).toBeUndefined();
  });

  it('allows a single-tag family (bare grand ref) to migrate', async () => {
    familyConfig('main', ['main']);
    await migrateRepo('shop', { to: 'm2' });
    expect(h.written).toEqual({ machine: 'm2' });
  });
});

describe('repo migrate — source disposition (R3)', () => {
  it('deletes the source image after a successful migrate', async () => {
    await migrateRepo('shop', { to: 'm2' });
    expect(h.deletedRepos).toEqual(['shop']);
  });

  it('retains the source under --keep-source', async () => {
    await migrateRepo('shop', { to: 'm2', keepSource: true });
    expect(h.deletedRepos).toHaveLength(0);
  });
});
