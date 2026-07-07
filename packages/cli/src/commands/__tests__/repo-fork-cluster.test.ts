import { afterEach, describe, expect, it, vi } from 'vitest';
import { createEmptyRdcConfig } from '../../schema/schemas.js';
import { createCluster } from '../../services/cluster/cluster-provision.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { localExecutorService } from '../../services/executor/local-executor.js';
import type { ClusterConfig, RdcConfig } from '../../types/index.js';
import { handleClusterForkSeam } from '../repo-fork.js';

// The --provider path provisions the destination cluster before forking; stub
// the provisioner so the test never touches OpenTofu/SSH.
vi.mock('../../services/cluster/cluster-provision.js', () => ({
  createCluster: vi.fn().mockResolvedValue(undefined),
}));

const k8s: ClusterConfig = {
  provider: 'kvm',
  pools: [{ name: 'k8s', role: 'k8s-server', count: 1 }],
};

function buildConfig(): RdcConfig {
  const cfg = createEmptyRdcConfig();
  cfg.resources = {
    machines: {
      'prod-k8s-1': { ip: '1.1.1.1', user: 'root', cluster: { cluster: 'prod', pool: 'k8s' } },
      'other-k8s-1': { ip: '2.2.2.2', user: 'root', cluster: { cluster: 'other', pool: 'k8s' } },
    },
    storages: {},
    clusters: { prod: k8s, other: k8s },
  };
  return cfg;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(createCluster).mockClear();
});

describe('handleClusterForkSeam dispatch + destination selection (D13)', () => {
  it('forks into the source cluster via kube_namespace_fork on its control node', async () => {
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig());
    vi.spyOn(outputService, 'info').mockReturnValue(undefined);
    vi.spyOn(outputService, 'success').mockReturnValue(undefined);
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true, allSteps: [] } as never);

    await handleClusterForkSeam('shop', 'joseph', { cluster: 'prod' });

    expect(exec).toHaveBeenCalledTimes(1);
    const arg = exec.mock.calls[0][0];
    expect(arg.functionName).toBe('kube_namespace_fork');
    expect(arg.machineName).toBe('prod-k8s-1');
    expect(arg.kubeCluster).toBe('prod');
    // Same-cluster ceph fork: pv_backend 'auto' lets renet pick the CoW RBD
    // clone server-side, and the rbd path needs a datastore root.
    expect(arg.params).toMatchObject({
      namespace: 'shop',
      tag: 'joseph',
      cluster: 'prod',
      pv_backend: 'auto',
    });
    expect(arg.params?.datastore).toBeTruthy();
    // ceph_pool is resolved server-side from the source namespace marker.
    expect(arg.params).not.toHaveProperty('ceph_pool');
    expect(String(arg.params?.mount_path)).toContain('prod');
  });

  it('--to-cluster wins over --cluster as the fork destination', async () => {
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig());
    vi.spyOn(outputService, 'info').mockReturnValue(undefined);
    vi.spyOn(outputService, 'success').mockReturnValue(undefined);
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true, allSteps: [] } as never);

    await handleClusterForkSeam('shop', 'joseph', { cluster: 'prod', toCluster: 'other' });

    const arg = exec.mock.calls[0][0];
    expect(arg.machineName).toBe('other-k8s-1');
    expect(arg.kubeCluster).toBe('other');
    expect(arg.params).toMatchObject({ cluster: 'other' });
  });

  it('--provider provisions the destination cluster with createCluster, then forks into it', async () => {
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig());
    vi.spyOn(outputService, 'info').mockReturnValue(undefined);
    vi.spyOn(outputService, 'success').mockReturnValue(undefined);
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true, allSteps: [] } as never);

    await handleClusterForkSeam('shop', 'joseph', { provider: 'linode', toCluster: 'prod' });

    expect(vi.mocked(createCluster)).toHaveBeenCalledWith('prod', expect.anything());
    const arg = exec.mock.calls[0][0];
    expect(arg.functionName).toBe('kube_namespace_fork');
    expect(arg.kubeCluster).toBe('prod');
    // createCluster must provision the destination BEFORE the fork dispatch.
    const createOrder = vi.mocked(createCluster).mock.invocationCallOrder[0];
    const execOrder = exec.mock.invocationCallOrder[0];
    expect(createOrder).toBeLessThan(execOrder);
  });

  it('--provider without a destination cluster errors before dispatch', async () => {
    const exec = vi.spyOn(localExecutorService, 'execute');
    // The error goes through handleError, which calls process.exit — stub it.
    const exit = vi.spyOn(process, 'exit').mockImplementation((() => undefined) as never);
    vi.spyOn(outputService, 'error').mockReturnValue(undefined);

    await handleClusterForkSeam('shop', 'joseph', { provider: 'linode' });

    expect(exit).toHaveBeenCalled();
    expect(exec).not.toHaveBeenCalled();
    expect(vi.mocked(createCluster)).not.toHaveBeenCalled();
  });
});
