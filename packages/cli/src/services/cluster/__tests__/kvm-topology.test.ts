import { describe, expect, it } from 'vitest';
import type { ClusterConfig } from '../../../types/index.js';
import { resolveKvmTopology, vmIp } from '../kvm-topology.js';

const kvm = { netName: 'renet12', netBase: '192.168.112', controlId: 1 };

function cluster(overrides: Partial<ClusterConfig> = {}): ClusterConfig {
  const base: ClusterConfig = {
    provider: 'kvm',
    pools: [
      { name: 'srv', role: 'k8s-server', count: 1 },
      { name: 'agents', role: 'k8s-agent', count: 2 },
      { name: 'storage', role: 'ceph', count: 3 },
    ],
    kvm,
  };
  return { ...base, ...overrides };
}

describe('vmIp', () => {
  it('derives the address renet uses: netBase.(netOffset + vmId)', () => {
    expect(vmIp('192.168.112', 0, 11)).toBe('192.168.112.11');
    expect(vmIp('192.168.112', 100, 11)).toBe('192.168.112.111');
  });
});

describe('resolveKvmTopology', () => {
  it('routes ceph pools to the ceph id space and everything else to workers', () => {
    const t = resolveKvmTopology('c', cluster());
    expect(t.network.workerIds).toEqual([11, 12, 13]);
    expect(t.network.cephIds).toEqual([21, 22, 23]);
    expect(t.network.bridgeId).toBe(1);
    expect(t.network.netName).toBe('renet12');
  });

  it('numbers members 1-based per pool, matching materializeClusterMachines', () => {
    const t = resolveKvmTopology('c', cluster());
    const agents = t.members.filter((m) => m.pool === 'agents');
    expect(agents.map((m) => m.index)).toEqual([1, 2]);
    expect(agents.map((m) => m.ip)).toEqual(['192.168.112.12', '192.168.112.13']);
  });

  it('never allocates the control id to a member', () => {
    const t = resolveKvmTopology('c', cluster({ kvm: { ...kvm, controlId: 11 } }));
    expect(t.members.map((m) => m.vmId)).not.toContain(11);
  });

  // ops down tears VMs down by id, so a pool that grows must keep the ids its
  // running members already hold.
  it('reuses persisted ids and only allocates for the new members', () => {
    const existing = cluster({
      pools: [{ name: 'agents', role: 'k8s-agent', count: 3 }],
      kvm: { ...kvm, memberIds: { agents: [11, 12] } },
    });
    const t = resolveKvmTopology('c', existing);
    expect(t.memberIds.agents).toEqual([11, 12, 13]);
  });

  it('keeps ids stable when a pool shrinks', () => {
    const shrunk = cluster({
      pools: [{ name: 'agents', role: 'k8s-agent', count: 1 }],
      kvm: { ...kvm, memberIds: { agents: [11, 12, 13] } },
    });
    expect(resolveKvmTopology('c', shrunk).memberIds.agents).toEqual([11]);
  });

  it('refuses a cluster with no kvm topology', () => {
    expect(() => resolveKvmTopology('c', cluster({ kvm: undefined }))).toThrow(/no kvm topology/);
  });

  it('refuses hyperconverged pools, which the ops model cannot express', () => {
    const hyper = cluster({ pools: [{ name: 'all', role: 'hyperconverged', count: 2 }] });
    expect(() => resolveKvmTopology('c', hyper)).toThrow(/hyperconverged/);
  });
});
