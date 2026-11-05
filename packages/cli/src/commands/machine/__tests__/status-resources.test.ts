import type {
  ListResult,
  RepositoryInfo,
  RepositoryResources,
} from '@rediacc/shared/renet-contract/data/list-types.generated';
import { describe, expect, it } from 'vitest';
import { NO_MEMORY_CAP, repoResourceCells, uncappedRepoNames } from '../status.js';

const GIB = 1024 ** 3;
const MIB = 1024 ** 2;

function resources(over: Partial<RepositoryResources>): RepositoryResources {
  return {
    cpu_max: 'max 100000',
    cpu_usage_usec: 0,
    io_max: '',
    memory_current: 512 * MIB,
    memory_high: 0,
    memory_max: 0,
    oom_kills: 0,
    pids_current: 1,
    pids_max: 0,
    ram_size: 0,
    ram_used: 0,
    ...over,
  };
}

function repo(name: string, res?: RepositoryResources): RepositoryInfo {
  return { name, repo_name: name, resources: res } as unknown as RepositoryInfo;
}

describe('machine status resource cells (PLAN-repo-resource-limits R5)', () => {
  it('shows memory current / max, the OOM kills and the RAM volume used / size', () => {
    expect(
      repoResourceCells(
        resources({ memory_max: GIB, oom_kills: 3, ram_size: 256 * MIB, ram_used: 64 * MIB })
      )
    ).toEqual({ memory: '512.0 MB / 1.0 GB', oomKills: 3, ram: '64.0 MB / 256.0 MB' });
  });

  it('marks a repository with no memory.max, and shows - with no resources section', () => {
    expect(repoResourceCells(resources({})).memory).toBe(`512.0 MB / ${NO_MEMORY_CAP}`);
    expect(repoResourceCells(resources({})).ram).toBe('-');
    expect(repoResourceCells(undefined)).toEqual({ memory: '-', oomKills: '-', ram: '-' });
  });

  it('lists the uncapped repositories, skipping capped and unmounted ones', () => {
    const list = {
      repositories: [
        repo('capped', resources({ memory_max: GIB })),
        repo('open', resources({})),
        repo('unmounted'),
      ],
    } as unknown as ListResult;
    const names = uncappedRepoNames(list, (guid) => ({ name: guid, source: 'config' }));
    expect(names).toEqual(['open']);
  });
});
