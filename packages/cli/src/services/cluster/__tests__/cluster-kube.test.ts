import { afterEach, describe, expect, it, vi } from 'vitest';
import { createEmptyRdcConfig } from '../../../schema/schemas.js';
import type { ClusterConfig, MachineConfig, RdcConfig } from '../../../types/index.js';
import { configService } from '../../config/config-resources.js';
import { auditService } from '../../core/audit.js';
import { outputService } from '../../core/output.js';
import { localExecutorService } from '../../executor/local-executor.js';
import { forkCluster, installK8s, migrateCluster } from '../cluster-kube.js';

// A 2-node k8s cluster: server on prod-cp-1, agent on prod-w-1.
const k8sCluster: ClusterConfig = {
  provider: 'kvm',
  pools: [
    { name: 'cp', role: 'k8s-server', count: 1 },
    { name: 'w', role: 'k8s-agent', count: 1 },
  ],
};

const memberIps: Record<string, string> = {
  'prod-cp-1': '192.168.111.11',
  'prod-w-1': '192.168.111.12',
  'dest-cp-1': '192.168.111.21',
  'dest-w-1': '192.168.111.22',
  'relocate-target': '192.168.111.99',
};

function buildConfig(clusters: Record<string, ClusterConfig>): RdcConfig {
  const cfg = createEmptyRdcConfig();
  cfg.resources = { machines: {}, storages: {}, clusters };
  return cfg;
}

function stubOutput(): void {
  vi.spyOn(outputService, 'info').mockReturnValue(undefined);
  vi.spyOn(outputService, 'success').mockReturnValue(undefined);
  vi.spyOn(outputService, 'warn').mockReturnValue(undefined);
}

function stubConfig(clusters: Record<string, ClusterConfig>): void {
  vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig(clusters));
  vi.spyOn(configService, 'getLocalMachine').mockImplementation((name: string) =>
    Promise.resolve({ ip: memberIps[name] ?? '10.0.0.1', user: 'root' } as MachineConfig)
  );
  let net = 3072;
  vi.spyOn(configService, 'allocateNetworkId').mockImplementation(() => {
    const v = net;
    net += 64;
    return Promise.resolve(v);
  });
  vi.spyOn(auditService, 'recordOperation').mockReturnValue(undefined);
}

function execMock() {
  return vi.spyOn(localExecutorService, 'execute').mockImplementation((opts) => {
    // The join-token read returns a CA-derived token on stdout.
    if (opts.functionName === 'kube_join_token') {
      return Promise.resolve({
        success: true,
        stdout: '{"token":"K10abcdef::server:0123456789abcdef"}',
      } as never);
    }
    return Promise.resolve({ success: true } as never);
  });
}

afterEach(() => vi.restoreAllMocks());

describe('installK8s (wave 7 multi-node bring-up)', () => {
  it('installs the server on its real NIC, then joins each agent with the CA token', async () => {
    stubOutput();
    stubConfig({ prod: k8sCluster });
    const exec = execMock();

    await installK8s('prod', k8sCluster.pools, false);

    const calls = exec.mock.calls.map((c) => c[0]);
    expect(calls.map((c) => c.functionName)).toEqual([
      'repository_create', // server image
      'kube_install', // server
      'kube_join_token', // read token
      'repository_create', // agent image
      'kube_join', // agent
    ]);

    const install = calls.find((c) => c.functionName === 'kube_install');
    expect(install?.machineName).toBe('prod-cp-1');
    expect(install?.params).toMatchObject({ role: 'server', bind_ip: '192.168.111.11' });

    const join = calls.find((c) => c.functionName === 'kube_join');
    expect(join?.machineName).toBe('prod-w-1');
    expect(join?.params).toMatchObject({
      role: 'agent',
      bind_ip: '192.168.111.12',
      endpoint: 'https://192.168.111.11:6443',
      token: 'K10abcdef::server:0123456789abcdef',
    });
  });
});

describe('forkCluster (wave 7 whole-cluster fork)', () => {
  it('refuses a fork with no destination (co-tenancy: two k3s cannot share a host netns)', async () => {
    stubOutput();
    stubConfig({ prod: k8sCluster });
    execMock();
    await expect(forkCluster('prod', { tag: 'joseph' })).rejects.toThrow(/distinct machines/);
  });

  it('drains every source node before reflinking, control-plane first', async () => {
    stubOutput();
    stubConfig({ prod: k8sCluster, dest: k8sCluster });
    const exec = execMock();

    await forkCluster('prod', { tag: 'joseph', cluster: 'dest' });

    const names = exec.mock.calls.map((c) => c[0].functionName);
    // Both source nodes are prep-forked before any repository_fork runs.
    const firstReflink = names.indexOf('repository_fork');
    const prepCount = names.slice(0, firstReflink).filter((n) => n === 'kube_prep_fork').length;
    expect(prepCount).toBe(2);
    // The control-plane reflink + identity rewrite precede the agent's.
    const idxRewrites = exec.mock.calls
      .filter((c) => c[0].functionName === 'kube_identity_rewrite')
      .map((c) => c[0].params?.mode);
    expect(idxRewrites).toEqual(['server', 'agent']);
  });
});

describe('migrateCluster (wave 7 cross-machine relocate)', () => {
  it('stops the source, ships the image, and rewrites identity on the destination', async () => {
    stubOutput();
    stubConfig({
      prod: { provider: 'kvm', pools: [{ name: 'cp', role: 'k8s-server', count: 1 }] },
    });
    const exec = execMock();

    await migrateCluster('prod', { to: 'relocate-target' });

    const names = exec.mock.calls.map((c) => c[0].functionName);
    expect(names).toEqual([
      'kube_prep_fork',
      'repository_unmount',
      'backup_push',
      'repository_mount',
      'kube_identity_rewrite',
    ]);
    const push = exec.mock.calls.find((c) => c[0].functionName === 'backup_push');
    expect(push?.[0].params).toMatchObject({ target: 'machine', dest_host: '192.168.111.99' });
  });
});
