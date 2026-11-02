import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { localExecutorService } from '../../services/executor/local-executor.js';
import { executeRepoFunction } from '../repo-executor.js';

// The failure renderer exits the process outright in an agent environment; these tests read the exit code instead.
vi.mock('../agent-guard.js', () => ({ isAgentEnvironment: () => false }));
// The network ID is assumed recorded; discovery has its own suite (network-id-discovery.test.ts).
vi.mock('../../services/config/network-id-discovery.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/config/network-id-discovery.js')>()),
  ensureRepositoryNetworkId: () => Promise.resolve(2816),
}));

afterEach(() => {
  vi.restoreAllMocks();
  process.exitCode = undefined;
});

const msgs = { starting: 's', completed: 'c', failed: 'f' };

describe('executeRepoFunction threads the cluster target into execute()', () => {
  it('passes kubeCluster + the resolved control-node machine to localExecutorService.execute', async () => {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({
      repositoryGuid: 'g',
      tag: 'latest',
      credential: 'cred',
      networkId: 2816,
    });
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
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true, allSteps: [] } as never);

    await executeRepoFunction('repository_status', 'shop', 'server-1', {}, {}, msgs);

    expect(exec.mock.calls[0][0].kubeCluster).toBeUndefined();
    expect(exec.mock.calls[0][0].machineName).toBe('server-1');
  });
});

/**
 * ★ #74, the datastore CHOKEPOINT.
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
 * asking N call sites to remember, because a future verb would forget, exactly as
 * every existing one already had.
 *
 * ★ These are CHANNEL tests: they assert what actually REACHES the executor, not what
 * a command meant to send. An invariant test that only asks the caller about its
 * intent sails through green while a refactor silently severs the wire.
 *
 * ★★ And note WHY this was only ever caught on the kube path: #39's runtime assertion
 * made it AUDIBLE there (renet refuses when the declared runtime disagrees with the
 * datastore it resolves). In the DOCKER world there is no such assertion, so the same
 * divergence is silent, the kube path was not more broken, it was the only path that
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
    // Placement lives on the repo FAMILY, not the per-tag record. A fork must reach the same datastore as its parent, or it dispatches where its data is not.
    const exec = mockRepo();
    mockPlacement({ datastore: 'pds3' });

    await executeRepoFunction('repository_up', 'shop:test', 'cp-1', {}, {}, msgs);

    expect(exec.mock.calls[0][0].datastore).toBe('/mnt/rediacc-ds/pds3');
  });

  it('stays silent for a {machine} placement, so the machine default still applies', async () => {
    // The fallback is CORRECT for a machine with no named datastore. #74 is that the caller said nothing when it had something to say, not that the default exists. A gate that refuses everything protects nothing.
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

/**
 * The callers' contract: on a failed result executeRepoFunction has ALREADY rendered the failure and set a
 * failing exit code, so `backup browse`, `verify` and `snapshot` return without printing or setting one of their own.
 * Mocking the executor in a command test cannot catch this side losing the code, which is why it is pinned here.
 */
describe('executeRepoFunction fails closed on a failed result', () => {
  it.each([
    ['its own exit code', 3, 3],
    ['exit 1 for an exit code of 0', 0, 1],
    ['exit 1 for no exit code', undefined, 1],
  ])('sets %s', async (_label, exitCode, expected) => {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({
      repositoryGuid: 'g',
      tag: 'latest',
      credential: 'cred',
      networkId: 2816,
    });
    vi.spyOn(localExecutorService, 'execute').mockResolvedValue({
      success: false,
      exitCode,
      error: 'boom',
    } as never);
    const rendered = vi.spyOn(outputService, 'error').mockImplementation(() => undefined);

    const result = await executeRepoFunction('backup_verify', 'shop', 'server-1', {}, {}, msgs);

    expect(result.success).toBe(false);
    expect(process.exitCode).toBe(expected);
    expect(rendered).toHaveBeenCalledWith('boom');
  });
});

/**
 * `repo up` / `repo mount` of an existing repo must not re-allocate on renet's network-ID refusal: the
 * refusal surfaces as a STATE_MISMATCH naming the holder and the reconcile fix, not the generic text.
 */
describe('executeRepoFunction on a network-ID refusal', () => {
  const refusal = JSON.stringify({
    code: 'network_id_in_use',
    network_id: 2816,
    holder: { kind: 'repository', name: 'mail', datastore: WK_DATASTORE_PATH },
  });

  function failWith(stderr: string): void {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({
      repositoryGuid: 'g',
      tag: 'latest',
      credential: 'cred',
      networkId: 2816,
    });
    vi.spyOn(localExecutorService, 'execute').mockResolvedValue({
      success: false,
      exitCode: 1,
      stderr,
      error: 'boom',
    } as never);
    vi.spyOn(outputService, 'error').mockImplementation(() => undefined);
  }

  it.each(['repository_up', 'repository_mount'])(
    'throws the holder-naming text on %s',
    async (fn) => {
      failWith(`[relay] ${refusal}`);
      const call = executeRepoFunction(fn, 'shop', 'server-1', {}, {}, msgs);
      await expect(call).rejects.toMatchObject({ code: 'STATE_MISMATCH' });
      await expect(executeRepoFunction(fn, 'shop', 'server-1', {}, {}, msgs)).rejects.toThrow(
        /repository mail[\s\S]*rdc config reconcile/
      );
    }
  );

  it('keeps the generic failure for a verb that is not up or mount', async () => {
    failWith(refusal);
    const result = await executeRepoFunction('repository_status', 'shop', 'server-1', {}, {}, msgs);
    expect(result.success).toBe(false);
  });

  it('keeps the generic failure for an up that failed for another reason', async () => {
    failWith('compose: no such service');
    const result = await executeRepoFunction('repository_up', 'shop', 'server-1', {}, {}, msgs);
    expect(result.success).toBe(false);
  });
});
