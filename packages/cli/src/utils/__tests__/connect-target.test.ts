/**
 * `term connect <target>` / `vscode connect <target>` target resolution
 * (spec/03 §5.8, §5.9) and the §3.3 namespace-collision rule. One positional
 * addresses two namespaces (places and repos), so the resolution order — and
 * above all the refusal to guess — is the contract worth pinning.
 */

import type { RepoFamily } from '@rediacc/shared/config-schema';
import { createEmptyRdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { configService } from '../../services/config/config-resources.js';
import type { ClusterConfig, RdcConfig } from '../../types/index.js';
import { CliExitError } from '../cli-exit-error.js';
import { resolveConnectTarget } from '../repo-target.js';

const GUID = '11111111-1111-4111-8111-111111111111';

const prodCluster: ClusterConfig = {
  provider: 'kvm',
  pools: [{ name: 'k8s', role: 'k8s-server', count: 1 }],
};

function family(placement: RepoFamily['placement'], tags = ['main']): RepoFamily {
  return {
    grand: tags[0],
    tags: Object.fromEntries(tags.map((tag) => [tag, { repositoryGuid: GUID }])),
    ...(placement ? { placement } : {}),
  };
}

/**
 * A config with: two plain machines, a cluster (`prod`) whose control node is
 * its first k8s-server member, a docker repo (`shop`) on `standalone`, a
 * cluster-placed repo (`web`) on the cluster's data datastore, and two
 * deliberate collisions — `mail` is both a repo and a machine, `prod` is both a
 * repo and a cluster.
 */
function buildConfig(): RdcConfig {
  const cfg = createEmptyRdcConfig();
  cfg.resources = {
    machines: {
      standalone: { ip: '5.6.7.8', user: 'root' },
      mail: { ip: '5.6.7.9', user: 'root' },
      'prod-k8s-1': { ip: '1.2.3.4', user: 'root', cluster: { cluster: 'prod', pool: 'k8s' } },
    },
    storages: {},
    clusters: { prod: prodCluster },
    datastores: {
      'ds-k8s': {
        backend: { kind: 'rbd', pool: 'rbd', image: 'ds-k8s' },
        size: '10G',
        cluster: 'prod',
      },
    },
    repositories: {
      shop: family({ machine: 'standalone' }, ['main', 'test']),
      web: family({ datastore: 'ds-k8s' }, ['main']),
      mail: family({ machine: 'standalone' }, ['main']),
      prod: family({ machine: 'standalone' }, ['main']),
    },
  };
  cfg.state = { datastores: { 'ds-k8s': { attachedTo: 'prod-k8s-1' } } };
  return cfg;
}

async function expectExit(fn: () => Promise<unknown>, code: number): Promise<CliExitError> {
  let thrown: unknown;
  try {
    await fn();
  } catch (error) {
    thrown = error;
  }
  expect(thrown, 'expected a throw').toBeInstanceOf(CliExitError);
  const err = thrown as CliExitError;
  expect(err.exitCode).toBe(code);
  return err;
}

function mockConfig(): void {
  vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig());
}

afterEach(() => vi.restoreAllMocks());

describe('resolveConnectTarget — the place arm', () => {
  it('resolves a bare machine name to a machine shell', async () => {
    mockConfig();
    expect(await resolveConnectTarget('standalone')).toEqual({
      kind: 'place',
      machineName: 'standalone',
      label: 'standalone',
    });
  });

  it('resolves a cluster name to its control node, carrying the kubeCluster marker', async () => {
    mockConfig();
    expect(await resolveConnectTarget('prod-k8s-1')).toEqual({
      kind: 'place',
      machineName: 'prod-k8s-1',
      label: 'prod-k8s-1',
    });
  });
});

describe('resolveConnectTarget — the repo arm', () => {
  it('resolves a bare repo name to its derived machine (spec §2.3)', async () => {
    mockConfig();
    expect(await resolveConnectTarget('shop')).toEqual({
      kind: 'repo',
      machineName: 'standalone',
      label: 'standalone',
      repoKey: 'shop',
      repoName: 'shop',
      tag: 'main',
    });
  });

  it('resolves a tagged fork ref, keeping name:tag as the repo key', async () => {
    mockConfig();
    expect(await resolveConnectTarget('shop:test')).toEqual({
      kind: 'repo',
      machineName: 'standalone',
      label: 'standalone',
      repoKey: 'shop:test',
      repoName: 'shop',
      tag: 'test',
    });
  });

  it('resolves a cluster-placed repo to the control node plus its cluster', async () => {
    mockConfig();
    expect(await resolveConnectTarget('web')).toEqual({
      kind: 'repo',
      machineName: 'prod-k8s-1',
      kubeCluster: 'prod',
      label: 'prod',
      repoKey: 'web',
      repoName: 'web',
      tag: 'main',
    });
  });

  it('accepts a redundant @place on a repo ref', async () => {
    mockConfig();
    const target = await resolveConnectTarget('shop@standalone');
    expect(target).toMatchObject({ kind: 'repo', machineName: 'standalone', repoKey: 'shop' });
  });

  it('refuses a contradictory @place with exit 12, never retargeting', async () => {
    mockConfig();
    const err = await expectExit(() => resolveConnectTarget('shop@mail'), 12);
    expect(err.message).toContain('shop is placed at standalone');
  });
});

describe('resolveConnectTarget — the §3.3 collision rule', () => {
  it('refuses a bare name that is BOTH a repository and a machine (exit 11)', async () => {
    mockConfig();
    const err = await expectExit(() => resolveConnectTarget('mail'), 11);
    expect(err.message).toBe(
      'mail is both a repository and a machine. ' +
        'Use "term connect mail@<machine>" for the repository shell, ' +
        'or "term connect <machine-name>" for the machine shell.'
    );
  });

  it('refuses a bare name that is BOTH a repository and a cluster (exit 11)', async () => {
    mockConfig();
    const err = await expectExit(() => resolveConnectTarget('prod'), 11);
    expect(err.message).toContain('both a repository and a cluster');
  });

  it('an explicit @place disambiguates a collided name to the REPOSITORY', async () => {
    mockConfig();
    expect(await resolveConnectTarget('mail@standalone')).toMatchObject({
      kind: 'repo',
      machineName: 'standalone',
      repoKey: 'mail',
    });
  });

  it('an explicit :tag also disambiguates to the repository', async () => {
    mockConfig();
    expect(await resolveConnectTarget('shop:test')).toMatchObject({ kind: 'repo' });
  });

  it('exits 5 with candidates when the name is neither a repo nor a place', async () => {
    mockConfig();
    const err = await expectExit(() => resolveConnectTarget('nope'), 5);
    expect(err.message).toContain('neither a repository nor a machine');
    expect(err.details?.join('\n')).toContain('known repositories: mail, prod, shop, web');
    expect(err.details?.join('\n')).toContain('known machines and clusters:');
  });

  it('exits 2 on a grammar violation, before any namespace lookup', async () => {
    mockConfig();
    await expectExit(() => resolveConnectTarget('Shop_1'), 2);
  });
});
