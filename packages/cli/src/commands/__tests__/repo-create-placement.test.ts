/**
 * Placement union for `repo create` (spec/03 §5.4, the #38 fix).
 *
 * `repo create <name>` takes EXACTLY ONE of `--machine` (docker, implicit default
 * datastore) or `--datastore` (a named datastore, docker tiering, or the only
 * kubernetes form). The #38 fix is that a cluster repo lands on its DATA datastore
 * (the one `repo replicate` forks), not the control datastore. These tests assert
 * the flag arithmetic, the teaching errors, and, critically, that the birth
 * record carries the declared placement every derived-machine op resolves through.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { RdcConfig, RepositoryConfig } from '@rediacc/shared/config-schema';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExecuteOptions } from '../../services/executor/types.js';

const execute = vi.fn((_options: ExecuteOptions) =>
  Promise.resolve({ success: true, allSteps: [] })
);
const addRepository = vi.fn((_name: string, _config: RepositoryConfig) => Promise.resolve());
const getCurrent = vi.fn<() => Promise<RdcConfig>>();

const requestNetworkIdAuto = vi.fn();
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute }),
  requestNetworkIdAuto: (input: unknown) => requestNetworkIdAuto(input),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: vi.fn(() => Promise.resolve(undefined)),
    allocateNetworkId: vi.fn(() => Promise.resolve(42)),
    removeRepository: vi.fn(() => Promise.resolve()),
    getCurrent: () => getCurrent(),
    addRepository: (name: string, config: RepositoryConfig) => addRepository(name, config),
    getRepositoryKey: (name: string) => Promise.resolve(`${name}:latest`),
    getResourceState: () =>
      Promise.resolve({
        getRepositories: () => ({ 'shop:latest': { repositoryGuid: 'g', networkId: 42 } }),
        setRepositories: (repos: Record<string, RepositoryConfig>) => setRepositories(repos),
      }),
  },
}));
const setRepositories = vi.fn((_repos: Record<string, RepositoryConfig>) => Promise.resolve());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    setTimelineRendered: vi.fn(),
  },
}));
vi.mock('../../utils/agent-guard.js', () => ({ assertAgentRepoCreate: vi.fn() }));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn(() => Promise.resolve()) }));
vi.mock('../../utils/ssh-keygen.js', () => ({
  generateSSHKeyPair: () => ({ privateKey: 'priv', publicKey: 'pub' }),
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
// Keep namedDatastoreMount real-shaped but avoid pulling the heavy cluster-kube graph.
vi.mock('../../services/cluster/cluster-target.js', () => ({
  namedDatastoreMount: (d: string) => `/mnt/rediacc-ds/${d}`,
  clusterMountRemotePath: (c: string) => `${WK_DATASTORE_PATH}/mounts/${c}`,
}));

const handleError = vi.fn();
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  handleError: (e: unknown) => handleError(e),
}));

import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { setCommandJobDeps } from '../../services/jobs/command-job.js';
import { TicketStore } from '../../services/jobs/ticket-store.js';
import { handleRepoCreate } from '../repo-create-delete.js';

// The create runs as one job (PLAN-detached-jobs J16): a real ticket store in a temp directory, and a step claim that grants every claim, so the test sees the command's own plan.
let ticketDir: string;
const claimed: string[][] = [];
beforeEach(() => {
  ticketDir = mkdtempSync(join(tmpdir(), 'repo-create-'));
  claimed.length = 0;
  setCommandJobDeps({
    store: () => new TicketStore('test', ticketDir),
    stepDeps: () =>
      Promise.resolve({
        observer: { configName: 'test' },
        warn: () => undefined,
        claim: ({ steps, done }) => {
          if (!done) claimed.push(steps);
          return Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const })));
        },
      }),
  });
});
afterEach(() => {
  setCommandJobDeps();
  rmSync(ticketDir, { recursive: true, force: true });
});

/** The repository_create dispatch; the allocation floor's network_used query runs before it. */
function createCall(): ExecuteOptions {
  const call = execute.mock.calls.find((c) => c[0].functionName === 'repository_create');
  if (!call) throw new Error('repository_create was not dispatched');
  return call[0];
}

/** A config with the given datastores + machines, enough for placement resolution. */
// Fixtures are deliberately partial. Taking a loose record here is what lets the call sites pass a plain literal instead of casting each one through `as never`.
function config(
  over: Record<string, unknown> = {},
  state: Record<string, unknown> = {}
): RdcConfig {
  return {
    resources: { machines: {}, datastores: {}, ...over },
    state: { datastores: {}, ...state },
  } as unknown as RdcConfig;
}

describe('repo create placement union (#38)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getCurrent.mockResolvedValue(config());
  });

  it('refuses both --machine and --datastore (exit 2 teaching)', async () => {
    await handleRepoCreate('shop', { machine: 'm1', datastore: 'd1', size: '5G' });
    expect(addRepository).not.toHaveBeenCalled();
    expect(execute).not.toHaveBeenCalled();
    expect(handleError.mock.calls[0][0].exitCode ?? 2).toBe(2);
    expect(String(handleError.mock.calls[0][0].message)).toMatch(/exactly one placement flag/);
  });

  it('refuses neither flag (same teaching error)', async () => {
    await handleRepoCreate('shop', { size: '5G' });
    expect(addRepository).not.toHaveBeenCalled();
    expect(String(handleError.mock.calls[0][0].message)).toMatch(/exactly one placement flag/);
  });

  it('records placement {machine} and dispatches a docker create', async () => {
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });
    expect(handleError).not.toHaveBeenCalled();
    expect(addRepository).toHaveBeenCalledTimes(1);
    expect(addRepository.mock.calls[0][1]).toMatchObject({ placement: { machine: 'm1' } });
    expect(createCall()).toMatchObject({
      functionName: 'repository_create',
      machineName: 'm1',
      params: { repository: 'shop', size: '5G' },
    });
  });

  it('refuses --machine on a cluster-member machine (R2-F12)', async () => {
    getCurrent.mockResolvedValue(
      config({ machines: { m1: { cluster: { cluster: 'c1', pool: 'p' } } } })
    );
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });
    expect(addRepository).not.toHaveBeenCalled();
    expect(String(handleError.mock.calls[0][0].message)).toMatch(/member of cluster c1/);
  });

  it('refuses a docker placement with no --size', async () => {
    await handleRepoCreate('shop', { machine: 'm1' });
    expect(addRepository).not.toHaveBeenCalled();
    expect(String(handleError.mock.calls[0][0].message)).toMatch(/--size is required/);
  });

  it('places a docker-world datastore repo on the datastore mount (no cluster arm)', async () => {
    getCurrent.mockResolvedValue(
      config(
        {
          datastores: { tier1: { backend: { kind: 'rbd', pool: 'rbd', image: 'tier1' } } },
        },
        { datastores: { tier1: { attachedTo: 'm2' } } }
      )
    );
    await handleRepoCreate('shop', { datastore: 'tier1', size: '5G' });
    expect(handleError).not.toHaveBeenCalled();
    expect(addRepository.mock.calls[0][1]).toMatchObject({ placement: { datastore: 'tier1' } });
    const call = createCall() as {
      machineName: string;
      kubeCluster?: string;
      params: Record<string, unknown>;
    };
    expect(call.machineName).toBe('m2');
    expect(call.kubeCluster).toBeUndefined();
    expect(call.params).toMatchObject({ mount_path: '/mnt/rediacc-ds/tier1', size: '5G' });
    expect(call.params.cluster).toBeUndefined();
  });

  it('places a cluster (k8s) datastore repo with the kube arm, and refuses --size', async () => {
    getCurrent.mockResolvedValue(
      config(
        {
          datastores: {
            shopdata: {
              cluster: 'b1src',
              backend: { kind: 'rbd', pool: 'rbd', image: 'shopdata' },
            },
          },
        },
        { datastores: { shopdata: { attachedTo: 'cp-1' } } }
      )
    );
    // --size on a k8s placement is exit 2.
    await handleRepoCreate('shop', { datastore: 'shopdata', size: '5G' });
    expect(addRepository).not.toHaveBeenCalled();
    expect(String(handleError.mock.calls[0][0].message)).toMatch(/PVC declarations/);

    vi.clearAllMocks();
    getCurrent.mockResolvedValue(
      config(
        {
          datastores: {
            shopdata: {
              cluster: 'b1src',
              backend: { kind: 'rbd', pool: 'rbd', image: 'shopdata' },
            },
          },
        },
        { datastores: { shopdata: { attachedTo: 'cp-1' } } }
      )
    );
    await handleRepoCreate('shop', { datastore: 'shopdata' });
    expect(handleError).not.toHaveBeenCalled();
    expect(addRepository.mock.calls[0][1]).toMatchObject({ placement: { datastore: 'shopdata' } });
    const call = createCall() as {
      machineName: string;
      kubeCluster?: string;
      params: Record<string, unknown>;
    };
    expect(call.machineName).toBe('cp-1');
    expect(call.kubeCluster).toBe('b1src');
    // The #38 fix: the repo lands on its DATA datastore mount, with the cluster arm.
    expect(call.params).toMatchObject({
      mount_path: '/mnt/rediacc-ds/shopdata',
      cluster: 'b1src',
      start_docker: false,
    });
    expect(call.params.size).toBeUndefined();
  });

  /**
   * ★ #67, the dispatch must be ACCEPTABLE TO RENET, not merely well-formed.
   *
   * renet's `repository_create` reads the size with `GetSize(required=true)`
   * (pkg/datastore/registry.go), so a dispatch carrying no size is REFUSED with
   * "size required", UNLESS the caller declares `runtime: kube`, which is how renet
   * knows it is in the kubernetes world and must size volumes from the PVC
   * declarations instead (the #39 assertion channel).
   *
   * The CLI forbade `--size` on a k8s placement and then dispatched the DOCKER verb
   * with neither a size NOR a runtime. So renet refused every kube create: WITH
   * --size the CLI refused, and WITHOUT it renet did. There was no value of the flag
   * that worked, and `repo create` was unusable on the cluster path.
   *
   * This asserts renet's ACCEPTANCE RULE rather than the argv the CLI happens to
   * build. A test that only pinned the dispatch string would have passed while the
   * command was completely unusable, which is exactly how this shipped, and why the
   * kube case above (which asserts `size` is undefined) was green on a broken CLI.
   */
  function assertRenetWouldAccept(params: Record<string, unknown>): void {
    const hasSize = params.size !== undefined;
    const declaresKube = params.runtime === 'kube';
    expect(
      hasSize || declaresKube,
      'repository_create is unacceptable to renet: it requires a size unless the caller ' +
        `declares runtime=kube, and this dispatch has neither (size=${String(params.size)}, ` +
        `runtime=${String(params.runtime)}). renet would refuse it with "size required".`
    ).toBe(true);
  }

  it('dispatches a kube create renet can ACCEPT: no size, but runtime=kube (#67)', async () => {
    getCurrent.mockResolvedValue(
      config(
        {
          datastores: {
            shopdata: {
              cluster: 'b1src',
              backend: { kind: 'rbd', pool: 'rbd', image: 'shopdata' },
            },
          },
        },
        { datastores: { shopdata: { attachedTo: 'cp-1' } } }
      )
    );

    await handleRepoCreate('shop', { datastore: 'shopdata' });

    expect(handleError).not.toHaveBeenCalled();
    const call = createCall() as {
      functionName: string;
      params: Record<string, unknown>;
    };
    expect(call.functionName).toBe('repository_create');
    // A kube repo still carries NO size (its volumes come from the PVCs), so the ONLY thing that can make this dispatch acceptable is the runtime declaration.
    expect(call.params.size).toBeUndefined();
    assertRenetWouldAccept(call.params);
  });

  it('dispatches a docker create renet can ACCEPT: a size, and no kube claim (#67)', async () => {
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });

    expect(handleError).not.toHaveBeenCalled();
    const call = createCall() as { params: Record<string, unknown> };
    // The docker arm is acceptable the other way round: it carries a size, and it must NOT claim the kube runtime (renet asserts the declaration against the datastore descriptor and errors on a disagreement rather than silently picking an arm).
    expect(call.params.runtime).toBeUndefined();
    assertRenetWouldAccept(call.params);
  });

  /**
   * ★ #74, THE INVARIANT: the datastore DISPATCHED must be the datastore RECORDED.
   *
   * `repo create` resolved the placement (machine, cluster backref, mount path) and
   * then never told the executor about it. renet reads the datastore from the MACHINE
   * VAULT, so every create on a named datastore silently dispatched against the
   * machine's DEFAULT docker datastore, while the config recorded the named one. The
   * placement written to disk and the placement sent to the machine were two different
   * things, and nothing said so.
   *
   * This derives the expectation FROM the recorded config rather than hardcoding a
   * path: a test that pinned `datastore === '/mnt/rediacc-ds/shopdata'` would have
   * passed before this bug existed and would pass again the day it returns. The
   * invariant is the equality, not the string.
   */
  function assertDispatchMatchesRecordedPlacement(
    recorded: { placement?: { datastore?: string; machine?: string } },
    dispatched: { datastore?: string }
  ): void {
    const named = recorded.placement?.datastore;
    if (!named) {
      // A {machine} placement uses the machine's own default datastore: the caller
      // must NOT override it (that fallback is correct, and #74 is not about it).
      expect(dispatched.datastore).toBeUndefined();
      return;
    }
    expect(
      dispatched.datastore,
      `repo create recorded placement {datastore: "${named}"} in the config but dispatched ` +
        `against datastore "${String(dispatched.datastore)}". The config and the machine ` +
        'would diverge silently: renet resolves the datastore from the machine vault, so an ' +
        'undeclared datastore means the machine default, not the one the repo lives on.'
    ).toBe(`/mnt/rediacc-ds/${named}`);
  }

  it('dispatches against the datastore it RECORDED, not the machine default (#74)', async () => {
    getCurrent.mockResolvedValue(
      config(
        {
          datastores: {
            shopdata: {
              cluster: 'b1src',
              backend: { kind: 'rbd', pool: 'rbd', image: 'shopdata' },
            },
          },
        },
        { datastores: { shopdata: { attachedTo: 'cp-1' } } }
      )
    );

    await handleRepoCreate('shop', { datastore: 'shopdata' });

    expect(handleError).not.toHaveBeenCalled();
    const recorded = addRepository.mock.calls[0][1] as {
      placement?: { datastore?: string };
    };
    const dispatched = createCall() as { datastore?: string };
    assertDispatchMatchesRecordedPlacement(recorded, dispatched);
  });

  it('a docker-tiering datastore repo also dispatches against ITS datastore (#74)', async () => {
    // Not a kube-only bug: a docker repo on a NAMED datastore diverged the same way.
    getCurrent.mockResolvedValue(
      config(
        {
          datastores: { tier1: { backend: { kind: 'rbd', pool: 'rbd', image: 'tier1' } } },
        },
        { datastores: { tier1: { attachedTo: 'm2' } } }
      )
    );

    await handleRepoCreate('shop', { datastore: 'tier1', size: '5G' });

    expect(handleError).not.toHaveBeenCalled();
    const recorded = addRepository.mock.calls[0][1] as { placement?: { datastore?: string } };
    const dispatched = createCall() as { datastore?: string };
    assertDispatchMatchesRecordedPlacement(recorded, dispatched);
  });

  it('a {machine} placement keeps the machine default (the fallback is correct) (#74)', async () => {
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });

    expect(handleError).not.toHaveBeenCalled();
    const recorded = addRepository.mock.calls[0][1] as { placement?: { machine?: string } };
    const dispatched = createCall() as { datastore?: string };
    assertDispatchMatchesRecordedPlacement(recorded, dispatched);
  });

  it('exit 5 when the datastore is unknown; exit 12 when it is not attached', async () => {
    await handleRepoCreate('shop', { datastore: 'ghost', size: '5G' });
    expect(handleError.mock.calls[0][0].exitCode).toBe(5);

    vi.clearAllMocks();
    getCurrent.mockResolvedValue(
      config({ datastores: { d: { backend: { kind: 'rbd', pool: 'rbd', image: 'd' } } } })
    );
    await handleRepoCreate('shop', { datastore: 'd', size: '5G' });
    expect(handleError.mock.calls[0][0].exitCode).toBe(12);
  });
});

// PLAN-detached-jobs J16 (J0b finding 8): the create asks renet for the network ID inside the job, so the client neither probes `network_used` for a floor nor retries a refused ID.
describe('repo create network ID: renet allocates inside the job', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getCurrent.mockResolvedValue(config());
  });

  it('registers no ID, asks for "auto", and sends none in the params', async () => {
    const { configService } = await import('../../services/config/config-resources.js');
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });
    expect(handleError).not.toHaveBeenCalled();
    expect(configService.allocateNetworkId).not.toHaveBeenCalled();
    expect(addRepository.mock.calls[0][1]).not.toHaveProperty('networkId');
    expect(execute.mock.calls.map((c) => c[0].functionName)).toEqual(['repository_create']);
    expect(createCall().params).not.toHaveProperty('network_id');
    expect(requestNetworkIdAuto).toHaveBeenCalledWith(
      expect.objectContaining({ machine: 'm1', repoName: 'shop', recordAs: 'shop:latest' })
    );
    // The directive is the channel that sends network_id "auto" (executor-factory); the registered line names that value.
    const { outputService } = await import('../../services/core/output.js');
    const registered = vi
      .mocked(outputService.info)
      .mock.calls.map((c) => String(c[0]))
      .find((line) => line.includes('shop'));
    expect(registered).toContain('auto');
    expect(registered).not.toMatch(/\b42\b/);
  });

  it('keeps the created repo registered when finishing the outcome throws after the job ran', async () => {
    const { configService } = await import('../../services/config/config-resources.js');
    // The registration exists once addRepository ran, under the GUID it recorded.
    vi.mocked(configService.getRepository).mockImplementation(() => {
      const recorded = addRepository.mock.calls[0]?.[1];
      return Promise.resolve(recorded as never);
    });
    const { outputService } = await import('../../services/core/output.js');
    vi.mocked(outputService.success).mockImplementationOnce(() => {
      throw new Error('render broke');
    });
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });
    vi.mocked(configService.getRepository).mockImplementation(() => Promise.resolve(undefined));
    expect(execute.mock.calls.map((c) => c[0].functionName)).toEqual(['repository_create']);
    expect(configService.removeRepository).not.toHaveBeenCalled();
    expect(handleError).not.toHaveBeenCalled();
    expect(outputService.warn).toHaveBeenCalledWith(expect.stringContaining('was created'));
  });

  it('keeps the registration when the ticket store fails after the job was dispatched', async () => {
    const { configService } = await import('../../services/config/config-resources.js');
    vi.mocked(configService.getRepository).mockImplementation(() => {
      const recorded = addRepository.mock.calls[0]?.[1];
      return Promise.resolve(recorded as never);
    });
    class FailingStore extends TicketStore {
      override append(
        ...args: Parameters<TicketStore['append']>
      ): ReturnType<TicketStore['append']> {
        if (args[0] === 'finished') throw new Error('disk full');
        return super.append(...args);
      }
    }
    setCommandJobDeps({ store: () => new FailingStore('test', ticketDir) });
    const { outputService } = await import('../../services/core/output.js');
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });
    vi.mocked(configService.getRepository).mockImplementation(() => Promise.resolve(undefined));
    expect(execute.mock.calls.map((c) => c[0].functionName)).toEqual(['repository_create']);
    expect(configService.removeRepository).not.toHaveBeenCalled();
    expect(handleError).not.toHaveBeenCalled();
    expect(outputService.warn).toHaveBeenCalledWith(
      expect.stringContaining('its record could not be completed')
    );
    // The ticket id is printed once: JobDispatchedError's message already carries it (review 220611ec.1).
    const message = String(vi.mocked(outputService.warn).mock.calls.at(-1)?.[0]);
    expect(message.match(/ticket /g) ?? []).toHaveLength(1);
  });

  it('does not report a failed job as created when rendering its failure throws', async () => {
    const { renderLocalExecutionFailure } = await import('../../utils/local-execution-failures.js');
    vi.mocked(renderLocalExecutionFailure).mockImplementationOnce(() => {
      throw new Error('render broke');
    });
    execute.mockResolvedValueOnce({
      success: false,
      allSteps: [],
      exitCode: 1,
      state: 'failed',
      jobId: 'j-2',
    } as never);
    const { outputService } = await import('../../services/core/output.js');
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });
    expect(outputService.warn).not.toHaveBeenCalledWith(
      expect.stringContaining('finishing it failed')
    );
  });

  it('still rolls the registration back when the start was refused', async () => {
    const { configService } = await import('../../services/config/config-resources.js');
    vi.mocked(configService.getRepository).mockImplementation(() => {
      const recorded = addRepository.mock.calls[0]?.[1];
      return Promise.resolve(recorded as never);
    });
    execute.mockRejectedValueOnce(new Error('overlap'));
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });
    vi.mocked(configService.getRepository).mockImplementation(() => Promise.resolve(undefined));
    expect(configService.removeRepository).toHaveBeenCalled();
    expect(handleError).toHaveBeenCalled();
  });

  it('makes exactly one job for a refused ID, never a retry, with the rollback as its failure step', async () => {
    const refusal = JSON.stringify({ code: 'network_id_in_use', message: 'held', network_id: 42 });
    execute.mockResolvedValueOnce({
      success: false,
      allSteps: [],
      exitCode: 17,
      stderr: refusal,
      state: 'failed',
      jobId: 'j-1',
    } as never);
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });
    expect(
      execute.mock.calls.filter((c) => c[0].functionName === 'repository_create')
    ).toHaveLength(1);
    // The failure step is on the job's plan; the success steps are not run for a failed job.
    expect(createCall().jobSteps?.map((step) => step.name)).toEqual([
      'rollbackCreate',
      'identityRefresh',
      'reconcileBackupSchedules',
    ]);
  });

  it('defers the licence identity refresh to the identityRefresh step, with the size it was created with', async () => {
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });
    expect(createCall().deferIdentityRefresh).toBe(true);
    const refresh = createCall().jobSteps?.find((step) => step.name === 'identityRefresh');
    expect(refresh?.params).toMatchObject({
      function: 'repository_create',
      repository: 'shop',
      size: '5G',
    });
  });
});
