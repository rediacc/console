import { WK_INFRA_DOMAIN } from '@rediacc/shared/config/well-known.generated';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RdcConfig } from '../../../types/index.js';
import { configService } from '../../config/config-resources.js';
import {
  ensureForkLicense,
  forgetReplicaSet,
  getReplicaSet,
  listReplicaSets,
  planReplicas,
  type ReplicaRenderInput,
  recordReplicaSet,
  renderReplicaSet,
  replicaPlacement,
} from '../repo-replicate.js';

// The machine-slot pre-flight reaches the account server. Stub it: a unit test must not depend on whether the box running it happens to hold a live subscription token. Its own behaviour is covered in services/__tests__/license-preflight.test.ts.
vi.mock('../../account/license-preflight.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../account/license-preflight.js')>()),
  assertMachineSlotsAvailable: vi.fn().mockResolvedValue(undefined),
}));

// The fork licence step: the installed-licence read, issuance and the machine lease are all stubbed.
const licence = vi.hoisted(() => ({
  free: vi.fn().mockResolvedValue(undefined),
  token: vi.fn().mockResolvedValue(true),
  authority: vi.fn().mockResolvedValue('free'),
  statuses: vi.fn().mockResolvedValue([]),
  release: vi.fn(),
}));
vi.mock('../../account/free-license.js', () => ({
  issueFreeRepoLicense: licence.free,
  resolveLicenseAuthority: licence.authority,
}));
vi.mock('../../account/license.js', () => ({
  refreshRepoLicenseIdentity: licence.token,
  readRuntimeRepoLicenseStatuses: licence.statuses,
}));
vi.mock('../../account/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: vi.fn(),
}));
vi.mock('../../machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn().mockImplementation(() =>
      Promise.resolve({
        machine: { name: 'm' },
        sshPrivateKey: 'key',
        sftp: {},
        release: licence.release,
      })
    ),
  },
}));

afterEach(() => {
  vi.restoreAllMocks();
  licence.free.mockClear().mockResolvedValue(undefined);
  licence.token.mockClear().mockResolvedValue(true);
  licence.authority.mockClear().mockResolvedValue('free');
  licence.statuses.mockClear().mockResolvedValue([]);
  licence.release.mockClear();
});

const renderInput: ReplicaRenderInput = {
  repo: 'sqldb',
  repoGuid: 'guid-sqldb',
  setName: 'sqldb-replicas',
  datastore: 'ds-data',
  primaryApp: 'sqldb-primary',
  image: 'postgres:16',
  port: 5432,
  pvc: 'data',
  headless: false,
  replicas: [
    {
      index: 1,
      datastoreLabel: `${WK_INFRA_DOMAIN}/ds-ds-data-sqldb-replicas-r1`,
      mountPath: '/mnt/rediacc-ds/ds-data-sqldb-replicas-r1',
    },
    {
      index: 2,
      datastoreLabel: `${WK_INFRA_DOMAIN}/ds-ds-data-sqldb-replicas-r2`,
      mountPath: '/mnt/rediacc-ds/ds-data-sqldb-replicas-r2',
    },
  ],
};

describe('renderReplicaSet (spec 05 §1 manifest plumbing)', () => {
  it('renders one nodeAffinity-pinned local PV per replica + StatefulSet + two Services', () => {
    const yaml = renderReplicaSet(renderInput);
    // One PV per replica, each pinned to that replica's node datastore label.
    expect(yaml).toContain('name: sqldb-replicas-1-data');
    expect(yaml).toContain('name: sqldb-replicas-2-data');
    expect(yaml).toContain(`key: ${WK_INFRA_DOMAIN}/ds-ds-data-sqldb-replicas-r1`);
    // ★ #93 (storage speaks GUID, k8s objects speak name): the PV path into the fork mount is GUID-keyed, the fork is a byte-clone of the parent, whose volumes-open/CSI mount at mounts/volumes/<guid>/<vol>. A NAME-keyed path points at a directory that does not exist and the replica comes up EMPTY, so a regression back to the name must turn this red.
    expect(yaml).toContain(
      'path: /mnt/rediacc-ds/ds-data-sqldb-replicas-r1/mounts/volumes/guid-sqldb/data'
    );
    expect(yaml).not.toContain('mounts/volumes/sqldb/');
    // ...while the k8s OBJECTS keep the name: namespace + Services stay `sqldb`.
    expect(yaml).toContain('namespace: sqldb');
    // StatefulSet: N replicas, anti-affinity, REDIACC_ROLE=replica.
    expect(yaml).toContain('kind: StatefulSet');
    expect(yaml).toContain('replicas: 2');
    expect(yaml).toContain('podAntiAffinity');
    expect(yaml).toContain('value: replica');
    // claimRef pre-binds each PV to the PVC kubectl will mint from the volumeClaimTemplate: <template>-<sts>-<0-based ordinal>.
    expect(yaml).toContain('name: data-sqldb-replicas-0');
    expect(yaml).toContain('name: data-sqldb-replicas-1');
    // Two Services: -rw -> the PRIMARY app, -ro -> the replica-set label.
    expect(yaml).toContain('name: sqldb-rw');
    expect(yaml).toContain('app: sqldb-primary');
    expect(yaml).toContain('name: sqldb-ro');
    expect(yaml).toContain(`${WK_INFRA_DOMAIN}/replica-set: sqldb-replicas`);
  });

  it('--headless makes the read Service headless (clusterIP: None)', () => {
    const yaml = renderReplicaSet({ ...renderInput, headless: true });
    expect(yaml).toContain('clusterIP: None');
  });
});

describe('planReplicas and replicaPlacement', () => {
  const nodes = [
    { machine: 'n1', ip: '10.0.0.1' },
    { machine: 'n2', ip: '10.0.0.2' },
  ];

  it('spreads replicas round-robin, each under its derived fork key', () => {
    expect(planReplicas({ setName: 'set1', datastore: 'ds-data', replicas: 3, nodes })).toEqual([
      { index: 1, fork: 'ds-data:set1-r1', node: 'n1' },
      { index: 2, fork: 'ds-data:set1-r2', node: 'n2' },
      { index: 3, fork: 'ds-data:set1-r3', node: 'n1' },
    ]);
  });

  it('pins each PV to the fork label and its mount', () => {
    expect(replicaPlacement('ds-data', { index: 2, fork: 'ds-data:set1-r2', node: 'n2' })).toEqual({
      index: 2,
      datastoreLabel: `${WK_INFRA_DOMAIN}/ds-ds-data-set1-r2`,
      mountPath: '/mnt/rediacc-ds/ds-data-set1-r2',
    });
  });
});

describe('ensureForkLicense', () => {
  const FORK = 'ds-data:set1-r1';
  const run = () =>
    ensureForkLicense({ repo: 'sqldb', repoGuid: 'guid-sqldb' }, FORK, 'n1', 'id-fork-1');

  function givenRepo(grandGuid?: string): void {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({
      repositoryGuid: 'guid-sqldb',
      ...(grandGuid ? { grandGuid } : {}),
    } as never);
  }

  it('issues for the fork datastore id through the FREE licence, and releases the lease', async () => {
    givenRepo('grand-sqldb');
    await run();
    expect(licence.free.mock.calls[0][3]).toMatchObject({
      repositoryGuid: 'guid-sqldb',
      grandGuid: 'grand-sqldb',
      kind: 'fork',
      datastoreId: 'id-fork-1',
    });
    expect(licence.release).toHaveBeenCalled();
  });

  it('a grand repo without a grandGuid is its own grand', async () => {
    givenRepo();
    await run();
    expect(licence.free.mock.calls[0][3]).toMatchObject({ grandGuid: 'guid-sqldb' });
  });

  it('the subscription token path issues with the fork mount', async () => {
    givenRepo();
    licence.authority.mockResolvedValue('token');
    await run();
    expect(licence.free).not.toHaveBeenCalled();
    expect(licence.token.mock.calls[0][3]).toMatchObject({
      kind: 'fork',
      datastoreId: 'id-fork-1',
      datastoreMount: '/mnt/rediacc-ds/ds-data-set1-r1',
    });
  });

  it('the token path throws when the account issues nothing', async () => {
    givenRepo();
    licence.authority.mockResolvedValue('token');
    licence.token.mockResolvedValue(false);
    await expect(run()).rejects.toThrow(/did not issue a licence/);
  });

  it('a valid licence already installed for this id spends nothing', async () => {
    givenRepo();
    licence.statuses.mockResolvedValue([
      { repositoryGuid: 'guid-sqldb', datastoreId: 'id-fork-1', status: 'valid' },
    ]);
    await run();
    expect(licence.free).not.toHaveBeenCalled();
    expect(licence.token).not.toHaveBeenCalled();
    expect(licence.authority).not.toHaveBeenCalled();
    expect(licence.release).toHaveBeenCalled();
  });

  it.each([
    [
      'another datastore id',
      { repositoryGuid: 'guid-sqldb', datastoreId: 'id-parent', status: 'valid' },
    ],
    [
      'another repository',
      { repositoryGuid: 'guid-other', datastoreId: 'id-fork-1', status: 'valid' },
    ],
    [
      'an expired licence',
      { repositoryGuid: 'guid-sqldb', datastoreId: 'id-fork-1', status: 'expired' },
    ],
  ])('%s does not count as installed', async (_name, status) => {
    givenRepo();
    licence.statuses.mockResolvedValue([status]);
    await run();
    expect(licence.free).toHaveBeenCalledOnce();
  });

  it('a machine that cannot say what is installed stops the issuance', async () => {
    givenRepo();
    licence.statuses.mockRejectedValue(new Error('scan failed'));
    await expect(run()).rejects.toThrow(/scan failed/);
    expect(licence.free).not.toHaveBeenCalled();
    expect(licence.release).toHaveBeenCalled();
  });
});

describe('replica-set managed state (R2-F17 CRUD)', () => {
  it('record → list → get → forget round-trips through config state', async () => {
    let stored: Record<string, unknown> | undefined;
    vi.spyOn(configService, 'getCurrent').mockImplementation(
      () => Promise.resolve({ state: { replicaSets: stored } }) as never
    );
    vi.spyOn(configService, 'setStateBucket').mockImplementation((_key, sets) => {
      stored = sets as Record<string, unknown>;
      return Promise.resolve();
    });

    const set = {
      repo: 'sqldb',
      datastore: 'ds-data',
      cluster: 'prod',
      createdAt: '2026-07-11T00:00:00Z',
      replicas: [{ index: 1, fork: 'ds-data:s-r1', node: 'n1' }],
    };
    await recordReplicaSet('s', set);
    expect(await listReplicaSets()).toEqual({ s: set });
    expect(await getReplicaSet('s')).toEqual(set);
    await forgetReplicaSet('s');
    expect(await getReplicaSet('s')).toBeUndefined();
  });
});

// Ensure the RdcConfig type import is exercised (state shape).
const _typecheck: RdcConfig | undefined = undefined;
void _typecheck;
