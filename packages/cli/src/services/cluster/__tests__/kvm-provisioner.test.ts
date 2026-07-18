import { describe, expect, it } from 'vitest';
import type { ClusterConfig } from '../../../types/index.js';
import { clusterCephPool } from '../kvm-provisioner.js';

// #17: the ops phase must create the SAME pool the cluster/datastore path uses
// (default `rbd`), threaded via CEPH_POOL_NAME, so ops + install converge ONE
// pool instead of a `rediacc_rbd_pool` + `rbd` double-pool.
describe('clusterCephPool (#17 single-pool ops env)', () => {
  it('returns the cluster ceph pool for a ceph cluster (default rbd)', () => {
    const cfg: ClusterConfig = {
      provider: 'kvm',
      pools: [
        { name: 'cp', role: 'k8s-server', count: 1 },
        { name: 'storage', role: 'ceph', count: 2 },
      ],
    };
    expect(clusterCephPool(cfg)).toBe('rbd');
  });

  it('honors an explicit cluster.ceph.pool', () => {
    const cfg: ClusterConfig = {
      provider: 'kvm',
      pools: [
        { name: 'cp', role: 'k8s-server', count: 1 },
        { name: 'storage', role: 'ceph', count: 2 },
      ],
      ceph: { pool: 'app-pool' },
    };
    expect(clusterCephPool(cfg)).toBe('app-pool');
  });

  it('returns undefined for a cluster with no ceph pool (nothing to name)', () => {
    const cfg: ClusterConfig = {
      provider: 'kvm',
      pools: [{ name: 'cp', role: 'k8s-server', count: 1 }],
    };
    expect(clusterCephPool(cfg)).toBeUndefined();
  });
});
