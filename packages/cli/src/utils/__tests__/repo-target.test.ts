import { createEmptyRdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { configService } from '../../services/config/config-resources.js';
import type { ClusterConfig, RdcConfig } from '../../types/index.js';
import { assertDockerOnly, resolveRepoTarget } from '../repo-target.js';

// Minimal config: a standalone machine, a materialized k8s member, and cluster
// "prod" whose first k8s-server member (prod-k8s-1) is the control node.
function buildConfig(clusters: Record<string, ClusterConfig>): RdcConfig {
  const cfg = createEmptyRdcConfig();
  cfg.resources = {
    machines: {
      standalone: { ip: '5.6.7.8', user: 'root' },
      'prod-k8s-1': { ip: '1.2.3.4', user: 'root', cluster: { cluster: 'prod', pool: 'k8s' } },
    },
    storages: {},
    clusters,
  };
  return cfg;
}

const prodCluster: ClusterConfig = {
  provider: 'kvm',
  pools: [{ name: 'k8s', role: 'k8s-server', count: 1 }],
};

afterEach(() => vi.restoreAllMocks());

describe('resolveRepoTarget (repo-verb funnel entry)', () => {
  it('maps a machine target to itself with no kubeCluster', async () => {
    expect(await resolveRepoTarget({ machine: 'standalone' })).toEqual({
      machineName: 'standalone',
      kubeCluster: undefined,
    });
  });

  it('maps a cluster target to its control node + kubeCluster marker', async () => {
    vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig({ prod: prodCluster }));
    expect(await resolveRepoTarget({ cluster: 'prod' })).toEqual({
      machineName: 'prod-k8s-1',
      kubeCluster: 'prod',
    });
  });

  it('rejects specifying both -m and --cluster', async () => {
    await expect(resolveRepoTarget({ machine: 'm', cluster: 'c' })).rejects.toThrow(/only one/);
  });

  it('rejects specifying neither -m nor --cluster', async () => {
    await expect(resolveRepoTarget({})).rejects.toThrow(/required/);
  });
});

describe('assertDockerOnly (docker-only verb refusal)', () => {
  it('throws a clear docker-only error when --cluster is given', () => {
    expect(() => assertDockerOnly('takeover', { cluster: 'prod' })).toThrow(
      /Docker repositories only/
    );
  });

  it('is a no-op for a machine target', () => {
    expect(() => assertDockerOnly('takeover', {})).not.toThrow();
    expect(() => assertDockerOnly('tunnel', { cluster: undefined })).not.toThrow();
  });
});
