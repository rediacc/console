import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RepositoryConfig } from '../../types/index.js';
import { CliExitError } from '../../utils/cli-exit-error.js';

// i18n stub — return "key:{params}" so repo names interpolated into params are
// assertable in the produced strings (mirrors repo-secret.test.ts).
vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockListRepositories = vi.hoisted(() => vi.fn());
vi.mock('../config/config-resources.js', () => ({
  configService: { listRepositories: mockListRepositories },
}));

const mockWarn = vi.hoisted(() => vi.fn());
vi.mock('../core/output.js', () => ({
  outputService: { warn: (...a: unknown[]) => mockWarn(...a) },
}));

import {
  guardMachineRemoval,
  machineRemovePlacementError,
  reposPlacedOnMachine,
} from '../machine/machine-remove-guard.js';

function repo(name: string, config: Partial<RepositoryConfig>): {
  name: string;
  config: RepositoryConfig;
} {
  return { name, config: { repositoryGuid: '00000000-0000-0000-0000-000000000000', ...config } };
}

describe('reposPlacedOnMachine', () => {
  it('returns only repos whose placement DIRECTLY names the machine', () => {
    const repos = [
      repo('web', { placement: { machine: 'srv-1' } }),
      repo('api', { placement: { machine: 'srv-1' } }),
      repo('mail', { placement: { machine: 'srv-2' } }), // other machine
      repo('cache', { placement: { datastore: 'pool-a' } }), // datastore arm, not direct
      repo('legacy', {}), // no placement (migrated config)
    ];
    expect(reposPlacedOnMachine('srv-1', repos)).toEqual(['web', 'api']);
  });

  it('returns [] when nothing is placed on the machine', () => {
    expect(reposPlacedOnMachine('srv-1', [repo('mail', { placement: { machine: 'srv-2' } })])).toEqual(
      []
    );
  });
});

describe('machineRemovePlacementError', () => {
  it('is an exit-12 CliExitError naming the repos and the three verbs', () => {
    const err = machineRemovePlacementError('srv-1', ['web', 'api']);
    expect(err).toBeInstanceOf(CliExitError);
    expect(err.exitCode).toBe(12);
    // Repos are named in the message (via interpolated params) and in details.
    expect(err.message).toContain('web, api');
    expect(err.details).toEqual(['web', 'api']);
    // The three legitimate verbs are taught as next-action options.
    const runs = err.next?.options?.map((o) => o.run) ?? [];
    expect(runs.some((r) => r.startsWith('rdc repo migrate'))).toBe(true);
    expect(runs.some((r) => r.startsWith('rdc repo delete'))).toBe(true);
    expect(runs).toContain('rdc machine remove srv-1 --force');
  });
});

describe('guardMachineRemoval', () => {
  beforeEach(() => {
    mockListRepositories.mockReset();
    mockWarn.mockReset();
  });

  it('refuses with exit 12 and names the repos when placements reference the machine', async () => {
    const repos = [
      repo('web', { placement: { machine: 'srv-1' } }),
      repo('api', { placement: { machine: 'srv-1' } }),
      repo('mail', { placement: { machine: 'srv-2' } }),
    ];
    mockListRepositories.mockResolvedValue(repos);

    let thrown: unknown;
    try {
      await guardMachineRemoval('srv-1', false);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(CliExitError);
    const err = thrown as CliExitError;
    expect(err.exitCode).toBe(12);
    expect(err.message).toContain('web, api');
    expect(err.details).toEqual(['web', 'api']);
    expect(mockWarn).not.toHaveBeenCalled();
  });

  it('with --force proceeds and leaves the placements dangling (warns, does not mutate repos)', async () => {
    const repos = [
      repo('web', { placement: { machine: 'srv-1' } }),
      repo('api', { placement: { machine: 'srv-1' } }),
    ];
    mockListRepositories.mockResolvedValue(repos);

    await expect(guardMachineRemoval('srv-1', true)).resolves.toBeUndefined();
    // Warns that the surviving placements now dangle, naming them.
    expect(mockWarn).toHaveBeenCalledOnce();
    expect(String(mockWarn.mock.calls[0][0])).toContain('web, api');
    // The guard never rewrote placements — they still point at the removed
    // machine (dangling by construction).
    expect(reposPlacedOnMachine('srv-1', repos)).toEqual(['web', 'api']);
  });

  it('is a silent no-op when no repository is placed on the machine', async () => {
    mockListRepositories.mockResolvedValue([repo('mail', { placement: { machine: 'srv-2' } })]);
    await expect(guardMachineRemoval('srv-1', false)).resolves.toBeUndefined();
    expect(mockWarn).not.toHaveBeenCalled();
  });
});
