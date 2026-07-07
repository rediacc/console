import { afterEach, describe, expect, it, vi } from 'vitest';
import { createEmptyRdcConfig } from '../../../schema/schemas.js';
import type { ClusterConfig, MachineConfig, RdcConfig } from '../../../types/index.js';
import { configService } from '../../config/config-resources.js';
import { outputService } from '../../core/output.js';
import { localExecutorService } from '../../executor/local-executor.js';
import { installCluster } from '../cluster-provision.js';

// A cluster whose ceph pool materializes into prod-ceph-1..3.
const cephCluster: ClusterConfig = {
  provider: 'kvm',
  pools: [{ name: 'ceph', role: 'ceph', count: 3, disks: [{ purpose: '/dev/vdb', size: '50G' }] }],
  ceph: { pool: 'k8s-pool' },
};

const k8sOnlyCluster: ClusterConfig = {
  provider: 'kvm',
  pools: [{ name: 'k8s', role: 'k8s-server', count: 1 }],
};

const memberIps: Record<string, string> = {
  'prod-ceph-1': '10.0.0.1',
  'prod-ceph-2': '10.0.0.2',
  'prod-ceph-3': '10.0.0.3',
};

function buildConfig(cluster: ClusterConfig): RdcConfig {
  const cfg = createEmptyRdcConfig();
  cfg.resources = { machines: {}, storages: {}, clusters: { prod: cluster } };
  return cfg;
}

function stubOutput(): void {
  vi.spyOn(outputService, 'info').mockReturnValue(undefined);
  vi.spyOn(outputService, 'success').mockReturnValue(undefined);
  vi.spyOn(outputService, 'warn').mockReturnValue(undefined);
}

afterEach(() => vi.restoreAllMocks());

describe('installCluster ceph dispatch (wave 6b)', () => {
  it('dispatches ceph_* functions ceph-first, in order, with the right params', async () => {
    stubOutput();
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig(cephCluster));
    vi.spyOn(configService, 'getLocalMachine').mockImplementation((name: string) =>
      Promise.resolve({ ip: memberIps[name], user: 'root' } as MachineConfig)
    );
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true } as never);

    await installCluster('prod');

    const calls = exec.mock.calls.map((c) => c[0]);
    // Ordered dispatch: prerequisites x3, bootstrap, cluster_create, pool_create.
    expect(calls.map((c) => c.functionName)).toEqual([
      'ceph_install_prerequisites',
      'ceph_install_prerequisites',
      'ceph_install_prerequisites',
      'ceph_bootstrap_cluster',
      'ceph_cluster_create',
      'ceph_pool_create',
    ]);

    // Prerequisites run on every member machine.
    expect(calls.slice(0, 3).map((c) => c.machineName)).toEqual([
      'prod-ceph-1',
      'prod-ceph-2',
      'prod-ceph-3',
    ]);

    // Bootstrap: monitor = first member IP, ceph cluster name "ceph".
    const bootstrap = calls[3];
    expect(bootstrap.machineName).toBe('prod-ceph-1');
    expect(bootstrap.params).toMatchObject({ cluster: 'ceph', monitor: '10.0.0.1' });

    // cluster_create: all member IPs comma-joined, osd_device from the disk.
    const clusterCreate = calls[4];
    expect(clusterCreate.machineName).toBe('prod-ceph-1');
    expect(clusterCreate.params).toMatchObject({
      cluster: 'ceph',
      nodes: '10.0.0.1,10.0.0.2,10.0.0.3',
      osd_device: '/dev/vdb',
    });

    // pool_create: application pool name from cluster.ceph.pool, no pg_num.
    const poolCreate = calls[5];
    expect(poolCreate.params).toMatchObject({ pool: 'k8s-pool', cluster: 'ceph' });
    expect(poolCreate.params).not.toHaveProperty('pg_num');
  });

  it('defaults osd_device to /dev/sdb when the ceph pool declares no disks', async () => {
    stubOutput();
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(
      buildConfig({
        provider: 'kvm',
        pools: [{ name: 'ceph', role: 'ceph', count: 1 }],
        ceph: { pool: 'rbd' },
      })
    );
    vi.spyOn(configService, 'getLocalMachine').mockResolvedValue({
      ip: '10.0.0.1',
      user: 'root',
    });
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true } as never);

    await installCluster('prod');

    const clusterCreate = exec.mock.calls
      .map((c) => c[0])
      .find((c) => c.functionName === 'ceph_cluster_create');
    expect(clusterCreate?.params).toMatchObject({ osd_device: '/dev/sdb' });
  });

  it('throws with renet’s error when a ceph step fails', async () => {
    stubOutput();
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig(cephCluster));
    vi.spyOn(configService, 'getLocalMachine').mockImplementation((name: string) =>
      Promise.resolve({ ip: memberIps[name], user: 'root' } as MachineConfig)
    );
    vi.spyOn(localExecutorService, 'execute').mockResolvedValue({
      success: false,
      error: 'osd device busy',
    } as never);

    await expect(installCluster('prod')).rejects.toThrow(/osd device busy/);
  });

  it('dispatches no ceph_* functions for a cluster with no ceph pool (installs k8s instead)', async () => {
    stubOutput();
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig(k8sOnlyCluster));
    vi.spyOn(configService, 'getLocalMachine').mockResolvedValue({
      ip: '10.0.0.9',
      user: 'root',
    });
    vi.spyOn(configService, 'allocateNetworkId').mockResolvedValue(3072);
    const exec = vi.spyOn(localExecutorService, 'execute').mockResolvedValue({
      success: true,
      stdout: '{"token":"K10abc::server:def"}',
    } as never);

    await installCluster('prod');

    const fns = exec.mock.calls.map((c) => c[0].functionName);
    // No ceph pool -> no ceph_* dispatch; the k8s control plane comes up instead.
    expect(fns.some((f) => f.startsWith('ceph_'))).toBe(false);
    expect(fns).toContain('kube_install');
  });
});
