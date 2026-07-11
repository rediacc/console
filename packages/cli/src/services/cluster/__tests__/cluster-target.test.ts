import { afterEach, describe, expect, it, vi } from 'vitest';
import { createEmptyRdcConfig } from '../../../schema/schemas.js';
import type {
  ClusterConfig,
  MachineConfig,
  RdcConfig,
  StorageConfig,
} from '../../../types/index.js';
import { assertUniqueResourceName, resolveControlNode } from '../../config/config-cluster-ops.js';
import { configService } from '../../config/config-resources.js';
import { resolveRemoteName } from '../../../utils/remote-resolve.js';
import {
  applyClusterConnectionContext,
  clusterKubeconfigRemotePath,
  resolveExecutionTarget,
} from '../cluster-target.js';

// A config with: a standalone machine, two materialized cluster members, a
// storage, and a cluster "prod" whose first k8s-server member is prod-k8s-1.
function buildConfig(clusters: Record<string, ClusterConfig>): RdcConfig {
  const cfg = createEmptyRdcConfig();
  cfg.resources = {
    machines: {
      standalone: { ip: '5.6.7.8', user: 'root' },
      'prod-k8s-1': { ip: '1.2.3.4', user: 'root', cluster: { cluster: 'prod', pool: 'k8s' } },
      'prod-ceph-1': { ip: '1.2.3.5', user: 'root', cluster: { cluster: 'prod', pool: 'ceph' } },
    },
    storages: { s3: { provider: 'rclone', vaultContent: {} } },
    clusters,
  };
  return cfg;
}

const prodCluster: ClusterConfig = {
  provider: 'kvm',
  pools: [
    { name: 'k8s', role: 'k8s-server', count: 2 },
    { name: 'ceph', role: 'ceph', count: 3 },
  ],
};

afterEach(() => vi.restoreAllMocks());

describe('cluster target resolution matrix', () => {
  it('resolveControlNode picks the first k8s-server member', async () => {
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig({ prod: prodCluster }));
    expect(await resolveControlNode('prod')).toBe('prod-k8s-1');
  });

  it('resolveControlNode honors an explicit controlNode', async () => {
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(
      buildConfig({
        prod: {
          provider: 'kvm',
          controlNode: 'prod-ceph-1',
          pools: [{ name: 'k8s', role: 'k8s-server', count: 1 }],
        },
      })
    );
    expect(await resolveControlNode('prod')).toBe('prod-ceph-1');
  });

  it('assertUniqueResourceName rejects machine, cluster, and projected-member collisions', async () => {
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig({ prod: prodCluster }));
    await expect(assertUniqueResourceName('standalone')).rejects.toThrow(/already a machine/);
    await expect(assertUniqueResourceName('prod')).rejects.toThrow(/already a cluster/);
    // prod-ceph-2 is not yet a machine but is a projected member of cluster prod.
    await expect(assertUniqueResourceName('prod-ceph-2')).rejects.toThrow(/projected member/);
    await expect(assertUniqueResourceName('fresh-name')).resolves.toBeUndefined();
  });

  it('resolveExecutionTarget maps a machine target to itself', async () => {
    expect(await resolveExecutionTarget({ machine: 'standalone' })).toEqual({
      machineName: 'standalone',
    });
  });

  it('resolveExecutionTarget maps a cluster target to its control node + kubeconfig', async () => {
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig({ prod: prodCluster }));
    const target = await resolveExecutionTarget({ cluster: 'prod' });
    expect(target.machineName).toBe('prod-k8s-1');
    expect(target.cluster).toBe('prod');
    // #11: the kubeconfig lives inside the anchor CONTROL DATASTORE mount, NOT
    // the legacy per-node repo mount (/mnt/rediacc/mounts/<cluster>/…).
    expect(target.kubeconfig).toBe('/mnt/rediacc-ds/ds-control-prod/.rediacc/k3s/kubeconfig.yaml');
  });

  it('resolveExecutionTarget enforces mutual exclusion and a required target', async () => {
    await expect(resolveExecutionTarget({ machine: 'm', cluster: 'c' })).rejects.toThrow(
      /only one/
    );
    await expect(resolveExecutionTarget({})).rejects.toThrow(/required/);
  });

  it('applyClusterConnectionContext injects the remote KUBECONFIG and pins a namespace with -r', () => {
    const details: { environment?: Record<string, string>; kubeNamespace?: string } = {
      environment: { DOCKER_HOST: 'unix:///should-not-survive' },
    };
    applyClusterConnectionContext(details, 'prod', 'shop');
    // KUBECONFIG is the control-node remote path (analog of DOCKER_HOST), not a
    // local cache path; namespace = the -r repo (a k8s repo IS namespace <repo>).
    expect(details.environment?.KUBECONFIG).toBe(clusterKubeconfigRemotePath('prod'));
    expect(details.environment?.DOCKER_HOST).toBe('unix:///should-not-survive');
    expect(details.kubeNamespace).toBe('shop');
  });

  it('applyClusterConnectionContext leaves namespace unset when no repo is given', () => {
    const details: { environment?: Record<string, string>; kubeNamespace?: string } = {};
    applyClusterConnectionContext(details, 'prod');
    expect(details.environment?.KUBECONFIG).toBe(clusterKubeconfigRemotePath('prod'));
    expect(details.kubeNamespace).toBeUndefined();
  });

  it('resolveRemoteName resolves machine, storage, cluster, and treats members as machines', async () => {
    const machine: MachineConfig = { ip: 'x', user: 'root' };
    const storage: StorageConfig = { provider: 'rclone', vaultContent: {} };
    vi.spyOn(configService, 'getLocalMachine').mockImplementation((name: string) => {
      if (name === 'standalone' || name === 'prod-ceph-1') return Promise.resolve(machine);
      throw new Error('no machine');
    });
    vi.spyOn(configService, 'getStorage').mockImplementation((name: string) => {
      if (name === 's3') return Promise.resolve(storage);
      throw new Error('no storage');
    });
    // The cluster branch of resolveRemoteName reads getCurrent via config-cluster-ops.
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig({ prod: prodCluster }));

    expect((await resolveRemoteName('standalone')).type).toBe('machine');
    // A materialized member IS a machine, so machine-first ordering wins.
    expect((await resolveRemoteName('prod-ceph-1')).type).toBe('machine');
    expect((await resolveRemoteName('s3')).type).toBe('storage');
    // The cluster's own name resolves as a cluster.
    expect((await resolveRemoteName('prod')).type).toBe('cluster');
  });
});
