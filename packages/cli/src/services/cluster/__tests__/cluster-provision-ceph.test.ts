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
    // ceph_health FAILS ⇒ ceph not yet bootstrapped ⇒ full bootstrap path runs.
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockImplementation((opts) =>
        Promise.resolve(
          (opts.functionName === 'ceph_health' ? { success: false } : { success: true }) as never
        )
      );

    await installCluster('prod');

    const calls = exec.mock.calls.map((c) => c[0]);
    // Ordered dispatch (excluding the ceph_health probe): prerequisites x3,
    // bootstrap, cluster_create, pool_create.
    expect(calls.map((c) => c.functionName).filter((n) => n !== 'ceph_health')).toEqual([
      'ceph_install_prerequisites',
      'ceph_install_prerequisites',
      'ceph_install_prerequisites',
      'ceph_bootstrap_cluster',
      'ceph_cluster_create',
      'ceph_pool_create',
    ]);

    // Prerequisites run on every member machine.
    expect(
      calls.filter((c) => c.functionName === 'ceph_install_prerequisites').map((c) => c.machineName)
    ).toEqual(['prod-ceph-1', 'prod-ceph-2', 'prod-ceph-3']);

    // Bootstrap: monitor = first member IP, ceph cluster name "ceph".
    const bootstrap = calls.find((c) => c.functionName === 'ceph_bootstrap_cluster');
    expect(bootstrap?.machineName).toBe('prod-ceph-1');
    expect(bootstrap?.params).toMatchObject({ cluster: 'ceph', monitor: '10.0.0.1' });

    // cluster_create: all member IPs comma-joined, osd_device from the disk.
    const clusterCreate = calls.find((c) => c.functionName === 'ceph_cluster_create');
    expect(clusterCreate?.machineName).toBe('prod-ceph-1');
    expect(clusterCreate?.params).toMatchObject({
      cluster: 'ceph',
      nodes: '10.0.0.1,10.0.0.2,10.0.0.3',
      osd_device: '/dev/vdb',
    });

    // pool_create: application pool name from cluster.ceph.pool, no pg_num.
    // A 3-OSD topology is NOT small, so no size/min_size override (#9: never
    // weaken the product default for >=3 OSDs).
    const poolCreate = calls.find((c) => c.functionName === 'ceph_pool_create');
    expect(poolCreate?.params).toMatchObject({ pool: 'k8s-pool', cluster: 'ceph' });
    expect(poolCreate?.params).not.toHaveProperty('pg_num');
    expect(poolCreate?.params).not.toHaveProperty('size');
    expect(poolCreate?.params).not.toHaveProperty('min_size');
  });

  it('creates a size 2 / min_size 1 pool on a small (<3 OSD) topology (#9)', async () => {
    stubOutput();
    // 2 ceph members, one disk each ⇒ 2 OSDs ⇒ size 3 would be undersized.
    const smallCluster: ClusterConfig = {
      provider: 'kvm',
      pools: [
        { name: 'ceph', role: 'ceph', count: 2, disks: [{ purpose: '/dev/vdb', size: '50G' }] },
      ],
      ceph: { pool: 'k8s-pool' },
    };
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig(smallCluster));
    vi.spyOn(configService, 'getLocalMachine').mockImplementation((name: string) =>
      Promise.resolve({ ip: memberIps[name] ?? '10.0.0.9', user: 'root' } as MachineConfig)
    );
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockImplementation((opts) =>
        Promise.resolve(
          (opts.functionName === 'ceph_health' ? { success: false } : { success: true }) as never
        )
      );

    await installCluster('prod');

    const poolCreate = exec.mock.calls
      .map((c) => c[0])
      .find((c) => c.functionName === 'ceph_pool_create');
    expect(poolCreate?.params).toMatchObject({
      pool: 'k8s-pool',
      cluster: 'ceph',
      size: 2,
      min_size: 1,
      pg_num: 32, // #17: small pg_num keeps <3-OSD topologies under mon_max_pg_per_osd
    });
  });

  it('honors a disk count>1 when deciding the OSD total (#9)', async () => {
    stubOutput();
    // 2 members × 2 disks each = 4 OSDs ⇒ NOT small ⇒ no size override.
    const bigDisks: ClusterConfig = {
      provider: 'kvm',
      pools: [
        {
          name: 'ceph',
          role: 'ceph',
          count: 2,
          disks: [{ purpose: '/dev/vdb', size: '50G', count: 2 }],
        },
      ],
      ceph: { pool: 'k8s-pool' },
    };
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig(bigDisks));
    vi.spyOn(configService, 'getLocalMachine').mockImplementation((name: string) =>
      Promise.resolve({ ip: memberIps[name] ?? '10.0.0.9', user: 'root' } as MachineConfig)
    );
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockImplementation((opts) =>
        Promise.resolve(
          (opts.functionName === 'ceph_health' ? { success: false } : { success: true }) as never
        )
      );

    await installCluster('prod');

    const poolCreate = exec.mock.calls
      .map((c) => c[0])
      .find((c) => c.functionName === 'ceph_pool_create');
    expect(poolCreate?.params).not.toHaveProperty('size');
  });

  it('skips bootstrap when ceph is already up (ops phase) and converges the pool (BUG #4)', async () => {
    stubOutput();
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig(cephCluster));
    vi.spyOn(configService, 'getLocalMachine').mockImplementation((name: string) =>
      Promise.resolve({ ip: memberIps[name], user: 'root' } as MachineConfig)
    );
    // ceph_health SUCCEEDS ⇒ a mon already answers ⇒ skip prereqs+bootstrap+cluster_create.
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockResolvedValue({ success: true } as never);

    await installCluster('prod');

    const fns = exec.mock.calls.map((c) => c[0].functionName);
    expect(fns).toContain('ceph_health');
    expect(fns).not.toContain('ceph_bootstrap_cluster');
    expect(fns).not.toContain('ceph_cluster_create');
    expect(fns).not.toContain('ceph_install_prerequisites');
    // The application pool is still converged (idempotent).
    expect(fns).toContain('ceph_pool_create');
  });

  it('distributes ceph client config from the mon to every k8s node before k8s bring-up', async () => {
    stubOutput();
    const mixed: ClusterConfig = {
      provider: 'kvm',
      pools: [
        { name: 'cp', role: 'k8s-server', count: 1 },
        { name: 'w', role: 'k8s-agent', count: 1 },
        { name: 'ceph', role: 'ceph', count: 1 },
      ],
      ceph: { pool: 'rbd_pool' },
    };
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig(mixed));
    vi.spyOn(configService, 'getLocalMachine').mockImplementation((name: string) =>
      Promise.resolve({ ip: memberIps[name] ?? '10.0.0.9', user: 'root' } as MachineConfig)
    );
    vi.spyOn(configService, 'allocateNetworkId').mockResolvedValue(4096);
    const exec = vi.spyOn(localExecutorService, 'execute').mockImplementation((opts) => {
      if (opts.functionName === 'ceph_health') {
        return Promise.resolve({ success: false } as never); // not yet bootstrapped
      }
      if (opts.functionName === 'ceph_client_config_export') {
        return Promise.resolve({
          success: true,
          stdout: JSON.stringify({ conf: 'Y29uZg==', keyring: 'a2V5' }),
        } as never);
      }
      if (opts.functionName === 'kube_join_token') {
        return Promise.resolve({ success: true, stdout: '{"token":"K10x::server:y"}' } as never);
      }
      return Promise.resolve({ success: true } as never);
    });

    await installCluster('prod');

    const names = exec.mock.calls.map((c) => c[0].functionName);
    const exportIdx = names.indexOf('ceph_client_config_export');
    const installIdxs = names
      .map((n, i) => (n === 'ceph_client_config_install' ? i : -1))
      .filter((i) => i >= 0);
    const kubeInstallIdx = names.indexOf('kube_install');
    // export once (on the mon), install on BOTH k8s nodes, all before kube_install.
    expect(exportIdx).toBeGreaterThan(names.indexOf('ceph_pool_create'));
    expect(installIdxs.length).toBe(2);
    expect(Math.max(...installIdxs)).toBeLessThan(kubeInstallIdx);
    // The export is captured from the ceph mon; installs carry the conf+keyring.
    expect(exec.mock.calls[exportIdx][0].machineName).toBe('prod-ceph-1');
    const firstInstall = exec.mock.calls[installIdxs[0]][0];
    expect(firstInstall.params).toMatchObject({ conf: 'Y29uZg==', keyring: 'a2V5' });
    // The anchor control datastore is ceph-backed (cluster has ceph).
    const create = exec.mock.calls
      .map((c) => c[0])
      .find((c) => c.functionName === 'datastore_create');
    expect(create?.params).toMatchObject({ backend: 'ceph', pool: 'rbd_pool', cluster: 'prod' });
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
    // ceph_health FAILS ⇒ full bootstrap path runs (so ceph_cluster_create fires).
    const exec = vi
      .spyOn(localExecutorService, 'execute')
      .mockImplementation((opts) =>
        Promise.resolve(
          (opts.functionName === 'ceph_health' ? { success: false } : { success: true }) as never
        )
      );

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
