import { afterEach, describe, expect, it, vi } from 'vitest';
import { createEmptyRdcConfig } from '../../../schema/schemas.js';
import type { ClusterConfig, MachineConfig, RdcConfig } from '../../../types/index.js';
import { configService } from '../../config/config-resources.js';
import { auditService } from '../../core/audit.js';
import { outputService } from '../../core/output.js';
import { localExecutorService } from '../../executor/local-executor.js';
import { evictCluster, joinCluster } from '../cluster-membership.js';

const cluster: ClusterConfig = {
  provider: 'kvm',
  pools: [
    { name: 'cp', role: 'k8s-server', count: 1 },
    { name: 'w', role: 'k8s-agent', count: 1 },
  ],
};

const machineIps: Record<string, string> = {
  'prod-cp-1': '192.168.111.11',
  adopted: '192.168.111.50',
};

function buildConfig(opts: {
  machines?: Record<string, MachineConfig>;
  stateDatastores?: Record<string, { attachedTo?: string }>;
}): RdcConfig {
  const cfg = createEmptyRdcConfig();
  cfg.resources = { machines: opts.machines ?? {}, storages: {}, clusters: { prod: cluster } };
  if (opts.stateDatastores) {
    cfg.state = { ...(cfg.state ?? {}), datastores: opts.stateDatastores };
  }
  return cfg;
}

function stub(
  machines: Record<string, MachineConfig>,
  stateDatastores?: Record<string, { attachedTo?: string }>
) {
  vi.spyOn(outputService, 'info').mockReturnValue(undefined);
  vi.spyOn(outputService, 'success').mockReturnValue(undefined);
  vi.spyOn(auditService, 'recordOperation').mockReturnValue(undefined);
  vi.spyOn(configService, 'getCurrent').mockResolvedValue(
    buildConfig({ machines, stateDatastores })
  );
  vi.spyOn(configService, 'getLocalMachine').mockImplementation((name: string) => {
    const m = machines[name] ?? { ip: machineIps[name] ?? '10.0.0.1', user: 'root' };
    return Promise.resolve(m as MachineConfig);
  });
  vi.spyOn(configService, 'allocateNetworkId').mockResolvedValue(4096);
}

function execMock() {
  return vi.spyOn(localExecutorService, 'execute').mockImplementation((opts) => {
    if (opts.functionName === 'kube_join_token') {
      return Promise.resolve({ success: true, stdout: '{"token":"K10abc::server:def"}' } as never);
    }
    return Promise.resolve({ success: true } as never);
  });
}

afterEach(() => vi.restoreAllMocks());

describe('joinCluster', () => {
  it('reads the token from the anchor datastore, creates the agent image, joins, and sets the backref', async () => {
    stub({ adopted: { ip: '192.168.111.50', user: 'root' } });
    const exec = execMock();
    const update = vi.spyOn(configService, 'updateMachine').mockResolvedValue(undefined);

    await joinCluster('adopted', { cluster: 'prod' });

    const calls = exec.mock.calls.map((c) => c[0]);
    expect(calls.map((c) => c.functionName)).toEqual([
      'kube_join_token',
      'repository_create',
      'kube_join',
    ]);
    // Token read from the control plane's anchor datastore mount.
    expect(calls[0]).toMatchObject({
      machineName: 'prod-cp-1',
      params: { mount_path: '/mnt/rediacc-ds/ds-control-prod' },
    });
    // Agent joins on its own per-node image mount, bound to its real NIC.
    expect(calls[2]).toMatchObject({
      machineName: 'adopted',
      params: {
        mount_path: '/mnt/rediacc/mounts/prod',
        role: 'agent',
        bind_ip: '192.168.111.50',
        endpoint: 'https://192.168.111.11:6443',
      },
    });
    // Membership backref recorded (repo create --machine refuses on it).
    expect(update).toHaveBeenCalledWith('adopted', { cluster: { cluster: 'prod', pool: 'w' } });
  });

  it('is a no-op when the machine is already in this cluster', async () => {
    stub({
      adopted: { ip: '192.168.111.50', user: 'root', cluster: { cluster: 'prod', pool: 'w' } },
    });
    const exec = execMock();
    await joinCluster('adopted', { cluster: 'prod' });
    expect(exec).not.toHaveBeenCalled();
  });

  it('refuses a machine already in a different cluster', async () => {
    stub({
      adopted: { ip: '192.168.111.50', user: 'root', cluster: { cluster: 'other', pool: 'w' } },
    });
    execMock();
    await expect(joinCluster('adopted', { cluster: 'prod' })).rejects.toThrow(/already a member/);
  });
});

describe('evictCluster', () => {
  it('drains + deletes the node by IP and clears the backref', async () => {
    stub({
      adopted: { ip: '192.168.111.50', user: 'root', cluster: { cluster: 'prod', pool: 'w' } },
    });
    const exec = execMock();
    const update = vi.spyOn(configService, 'updateMachine').mockResolvedValue(undefined);

    await evictCluster('adopted', {});

    const calls = exec.mock.calls.map((c) => c[0]);
    expect(calls.map((c) => c.functionName)).toEqual(['kube_node_remove']);
    expect(calls[0]).toMatchObject({
      machineName: 'prod-cp-1',
      params: { mount_path: '/mnt/rediacc-ds/ds-control-prod', node_ip: '192.168.111.50' },
    });
    expect(update).toHaveBeenCalledWith('adopted', { cluster: undefined });
  });

  it('refuses when the machine still mounts a named datastore', async () => {
    stub(
      { adopted: { ip: '192.168.111.50', user: 'root', cluster: { cluster: 'prod', pool: 'w' } } },
      { 'ds-alpha': { attachedTo: 'adopted' } }
    );
    execMock();
    await expect(evictCluster('adopted', {})).rejects.toThrow(/still mounts datastore/);
  });

  it('refuses a machine that is not a cluster member', async () => {
    stub({ adopted: { ip: '192.168.111.50', user: 'root' } });
    execMock();
    await expect(evictCluster('adopted', {})).rejects.toThrow(/not a member/);
  });
});
