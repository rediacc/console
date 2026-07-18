import { afterEach, describe, expect, it, vi } from 'vitest';
import { configService } from '../../services/config/config-resources.js';
import { localExecutorService } from '../../services/executor/local-executor.js';
import { executeRepoFunction } from '../repo-executor.js';

afterEach(() => vi.restoreAllMocks());

const msgs = { starting: 's', completed: 'c', failed: 'f' };

describe('executeRepoFunction threads the cluster target into execute()', () => {
  it('passes kubeCluster + the resolved control-node machine to localExecutorService.execute', async () => {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({
      repositoryGuid: 'g',
      tag: 'latest',
      credential: 'cred',
      networkId: 2816,
    });
    vi.spyOn(configService, 'ensureRepositoryNetworkId').mockResolvedValue(undefined as never);
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true, allSteps: [] } as never);

    await executeRepoFunction(
      'repository_up',
      'shop',
      'prod-k8s-1',
      { foo: 'bar' },
      { kubeCluster: 'prod', debug: true },
      msgs
    );

    expect(exec).toHaveBeenCalledTimes(1);
    const arg = exec.mock.calls[0][0];
    expect(arg.functionName).toBe('repository_up');
    expect(arg.machineName).toBe('prod-k8s-1');
    expect(arg.kubeCluster).toBe('prod');
    expect(arg.params).toMatchObject({ repository: 'shop', foo: 'bar' });
  });

  it('leaves kubeCluster undefined for a plain machine target', async () => {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({
      repositoryGuid: 'g',
      tag: 'latest',
      credential: 'cred',
      networkId: 2816,
    });
    vi.spyOn(configService, 'ensureRepositoryNetworkId').mockResolvedValue(undefined as never);
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true, allSteps: [] } as never);

    await executeRepoFunction('repository_status', 'shop', 'server-1', {}, {}, msgs);

    expect(exec.mock.calls[0][0].kubeCluster).toBeUndefined();
    expect(exec.mock.calls[0][0].machineName).toBe('server-1');
  });
});

/**
 * ★ #74 — the datastore CHOKEPOINT.
 *
 * `executeRepoFunction` drives essentially the ENTIRE repo family (up, down, status,
 * validate, ownership, template, ...), and NOT ONE of those verbs declared the
 * datastore its repo actually lives on. renet reads the datastore from the MACHINE
 * VAULT (`p.Datastore()`), never from the params bag, so the caller's SILENCE was the
 * bug: every verb dispatched against the machine's default docker datastore while the
 * config recorded the named one. The config and the machine described two different
 * places, and nothing said so.
 *
 * The datastore is derived ONCE here, from the repo's recorded placement, instead of
 * asking N call sites to remember — because a future verb would forget, exactly as
 * every existing one already had.
 *
 * ★ These are CHANNEL tests: they assert what actually REACHES the executor, not what
 * a command meant to send. An invariant test that only asks the caller about its
 * intent sails through green while a refactor silently severs the wire.
 *
 * ★★ And note WHY this was only ever caught on the kube path: #39's runtime assertion
 * made it AUDIBLE there (renet refuses when the declared runtime disagrees with the
 * datastore it resolves). In the DOCKER world there is no such assertion, so the same
 * divergence is silent — the kube path was not more broken, it was the only path that
 * could tell us.
 */
describe('executeRepoFunction declares the recorded datastore (#74)', () => {
  function mockRepo() {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({
      repositoryGuid: 'g',
      tag: 'latest',
      credential: 'cred',
      networkId: 2816,
    });
    vi.spyOn(configService, 'ensureRepositoryNetworkId').mockResolvedValue(undefined as never);
    return vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true, allSteps: [] } as never);
  }

  /** A config whose repo FAMILY carries the given placement. */
  function mockPlacement(placement: Record<string, string> | undefined) {
    vi.spyOn(configService, 'getCurrent').mockResolvedValue({
      resources: {
        repositories: placement ? { shop: { grand: 'latest', tags: {}, placement } } : {},
      },
    } as never);
  }

  it('dispatches against the NAMED datastore the repo is recorded on', async () => {
    const exec = mockRepo();
    mockPlacement({ datastore: 'pds3' });

    await executeRepoFunction('repository_up', 'shop', 'cp-1', {}, {}, msgs);

    expect(
      exec.mock.calls[0][0].datastore,
      'a repo verb must dispatch against the datastore the repo is RECORDED on; staying ' +
        'silent means renet uses the machine default, and the config and the machine then ' +
        'describe two different places'
    ).toBe('/mnt/rediacc-ds/pds3');
  });

  it('resolves the placement from the FAMILY, so a tagged ref reaches it too', async () => {
    // Placement lives on the repo FAMILY, not the per-tag record. A fork must reach the
    // same datastore as its parent, or it dispatches where its data is not.
    const exec = mockRepo();
    mockPlacement({ datastore: 'pds3' });

    await executeRepoFunction('repository_up', 'shop:test', 'cp-1', {}, {}, msgs);

    expect(exec.mock.calls[0][0].datastore).toBe('/mnt/rediacc-ds/pds3');
  });

  it('stays silent for a {machine} placement, so the machine default still applies', async () => {
    // The fallback is CORRECT for a machine with no named datastore. #74 is that the
    // caller said nothing when it had something to say, not that the default exists.
    // A gate that refuses everything protects nothing.
    const exec = mockRepo();
    mockPlacement({ machine: 'm1' });

    await executeRepoFunction('repository_up', 'shop', 'm1', {}, {}, msgs);

    expect(exec.mock.calls[0][0].datastore).toBeUndefined();
  });

  it('stays silent when the repo has no recorded placement at all', async () => {
    const exec = mockRepo();
    mockPlacement(undefined);

    await executeRepoFunction('repository_status', 'shop', 'm1', {}, {}, msgs);

    expect(exec.mock.calls[0][0].datastore).toBeUndefined();
  });
});
