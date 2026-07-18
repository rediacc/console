import type { CanarySet } from '@rediacc/shared/config-schema';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { configService } from '../../config/config-resources.js';
import { outputService } from '../../core/output.js';
import { localExecutorService } from '../../executor/local-executor.js';
import {
  __setReleaseClock,
  createCanary,
  releaseUndoSnapshot,
  removeCanary,
  renderCanaryOverlay,
  setCanaryWeight,
} from '../repo-release.js';

vi.mock('../cluster-target.js', () => ({
  resolveExecutionTarget: vi.fn(() => Promise.resolve({ machineName: 'cp1', cluster: 'prod' })),
}));

let stored: Record<string, CanarySet> | undefined;

function mockState(initial?: Record<string, CanarySet>): void {
  stored = initial;
  vi.spyOn(configService, 'getCurrent').mockImplementation(
    () => Promise.resolve({ state: { canaries: stored } }) as never
  );
  vi.spyOn(configService, 'setStateBucket').mockImplementation((_key, sets) => {
    stored = sets as Record<string, CanarySet>;
    return Promise.resolve();
  });
}

function execMock() {
  return vi.spyOn(localExecutorService, 'execute').mockResolvedValue({ success: true } as never);
}

beforeEach(() => {
  vi.spyOn(outputService, 'info').mockReturnValue(undefined);
  vi.spyOn(outputService, 'warn').mockReturnValue(undefined);
  vi.spyOn(outputService, 'success').mockReturnValue(undefined);
  __setReleaseClock(() => 1_800_000_000_000);
});
afterEach(() => vi.restoreAllMocks());

const seededCanary: CanarySet = {
  repo: 'shop',
  cluster: 'prod',
  service: 'web',
  image: 'shop:v2',
  port: 80,
  replicas: 1,
  weight: 10,
  undoSnapshot: 'release-undo-1',
  createdAt: '2026-07-11T00:00:00Z',
};

describe('releaseUndoSnapshot (rung 0)', () => {
  it('takes ONE group snapshot of the cluster before a release-class mutation', async () => {
    const exec = execMock();
    const name = await releaseUndoSnapshot('prod', 'cp1');
    expect(name).toBe('release-undo-1800000000000');
    const calls = exec.mock.calls.map((c) => c[0]);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({
      functionName: 'datastore_snapshot_create',
      machineName: 'cp1',
      params: { group: 'prod', snapshot: 'release-undo-1800000000000' },
    });
  });
});

describe('renderCanaryOverlay (rung 2 templating)', () => {
  it('renders one Deployment + one Service with the router canary contract', () => {
    const yaml = renderCanaryOverlay({
      repo: 'shop',
      service: 'web',
      image: 'shop:v2',
      port: 80,
      weight: 20,
      replicas: 2,
    });
    // Deployment: new image, canary role, overlay-set label for teardown.
    expect(yaml).toContain('kind: Deployment');
    expect(yaml).toContain('name: shop-canary');
    expect(yaml).toContain('image: shop:v2');
    expect(yaml).toContain('replicas: 2');
    expect(yaml).toContain('value: canary');
    expect(yaml).toContain('rediacc.io/replica-set: shop-canary');
    // Service: the annotations the renet router's canary rewrite consumes.
    expect(yaml).toContain('rediacc.canary_of: web');
    expect(yaml).toContain('rediacc.weight: "20"');
    expect(yaml).toContain('rediacc.service_port: "80"');
  });
});

describe('createCanary (create orchestrator)', () => {
  it('rung-0 snapshot FIRST, then applies the overlay and records state', async () => {
    mockState();
    const exec = execMock();

    await createCanary({
      repo: 'shop',
      cluster: 'prod',
      image: 'shop:v2',
      port: 80,
      weight: 10,
      service: 'web',
    });

    const calls = exec.mock.calls.map((c) => c[0]);
    expect(calls.map((c) => c.functionName)).toEqual([
      'datastore_snapshot_create', // rung 0 BEFORE the mutation
      'kube_apply',
    ]);
    expect(calls[0].params).toMatchObject({ group: 'prod' });
    expect(calls[1]).toMatchObject({
      machineName: 'cp1',
      params: {
        mount_path: '/mnt/rediacc-ds/ds-control-prod',
        namespace: 'shop',
        name: 'canary-shop-canary.yaml',
        cluster: 'prod',
      },
    });
    expect(calls[1].params?.manifest).toContain('rediacc.canary_of: web');
    expect(stored?.['shop-canary']).toMatchObject({
      repo: 'shop',
      service: 'web',
      weight: 10,
      undoSnapshot: 'release-undo-1800000000000',
    });
  });

  it('defaults the stable service to the repo name', async () => {
    mockState();
    const exec = execMock();
    await createCanary({ repo: 'shop', cluster: 'prod', image: 'i', port: 80, weight: 0 });
    const apply = exec.mock.calls.map((c) => c[0]).find((c) => c.functionName === 'kube_apply');
    expect(apply?.params?.manifest).toContain('rediacc.canary_of: shop');
    expect(stored?.['shop-canary']).toBeDefined();
  });

  it('refuses a duplicate canary and an out-of-range weight', async () => {
    mockState({ 'shop-canary': seededCanary });
    execMock();
    await expect(
      createCanary({
        repo: 'shop',
        cluster: 'prod',
        image: 'i',
        port: 80,
        weight: 10,
        service: 'web',
      })
    ).rejects.toThrow(/already has a canary/);
    await expect(
      createCanary({ repo: 'shop', cluster: 'prod', image: 'i', port: 80, weight: 101 })
    ).rejects.toThrow(/0\.\.100/);
  });
});

describe('setCanaryWeight (the nudge / the rung-3 flip)', () => {
  it('takes a FRESH undo snapshot, re-applies with the new weight, updates state', async () => {
    mockState({ 'shop-canary': seededCanary });
    const exec = execMock();

    await setCanaryWeight('shop', 100);

    const calls = exec.mock.calls.map((c) => c[0]);
    expect(calls.map((c) => c.functionName)).toEqual(['datastore_snapshot_create', 'kube_apply']);
    expect(calls[1].params?.manifest).toContain('rediacc.weight: "100"');
    expect(stored?.['shop-canary']).toMatchObject({
      weight: 100,
      undoSnapshot: 'release-undo-1800000000000',
      updatedAt: new Date(1_800_000_000_000).toISOString(),
    });
  });

  it('refuses an unknown set', async () => {
    mockState();
    execMock();
    await expect(setCanaryWeight('nope', 50)).rejects.toThrow(/has no canary/);
  });
});

describe('removeCanary (teardown)', () => {
  it('deletes the label-scoped overlay and forgets state (NO datastores touched)', async () => {
    mockState({ 'shop-canary': seededCanary });
    const exec = execMock();

    await removeCanary('shop');

    const calls = exec.mock.calls.map((c) => c[0]);
    expect(calls.map((c) => c.functionName)).toEqual(['kube_delete']);
    expect(calls[0].params).toMatchObject({ namespace: 'shop', replica_set: 'shop-canary' });
    expect(stored).toEqual({});
  });

  it('forgets state even when the overlay delete fails (converges)', async () => {
    mockState({ 'shop-canary': seededCanary });
    vi.spyOn(localExecutorService, 'execute').mockResolvedValue({
      success: false,
      error: 'cluster gone',
    } as never);
    await removeCanary('shop');
    expect(stored).toEqual({});
  });
});
