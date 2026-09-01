import type {
  ListResult,
  StorageHealthResult,
  SystemInfo,
} from '@rediacc/shared/renet-contract/data/list-types.generated';
import { describe, expect, it, vi } from 'vitest';

// status.ts pulls in i18n/config/output at import time; stub the side-effectful
// ones so we can exercise the pure helpers in isolation.
vi.mock('../../services/core/output.js', () => ({ outputService: { info: vi.fn() } }));
vi.mock('../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../i18n/index.js', () => ({ t: (k: string) => k }));

import { createRepoNameResolver } from '../../utils/guid-resolver.js';
import {
  buildStorageHealthRows,
  collectSections,
  deriveStorageSummary,
  fragmentationPerGb,
} from '../machine/status.js';

function makeSystem(diskAvail: string, dsAvail: string, dsTotal = '364.5G'): SystemInfo {
  return {
    disk: { total: '386.4G', used: '0G', available: diskAvail, use_percent: '0%' },
    datastore: {
      path: '/mnt/rediacc',
      total: dsTotal,
      used: '0G',
      available: dsAvail,
      use_percent: '0%',
    },
  } as unknown as SystemInfo;
}

describe('deriveStorageSummary', () => {
  it('returns null when system data is absent (no fabricated 0.0G)', () => {
    expect(deriveStorageSummary(undefined)).toBeNull();
    expect(deriveStorageSummary(makeSystem('', ''))).toBeNull();
  });

  it('reports datastore as the limiting resource when it has less free space', () => {
    const s = deriveStorageSummary(makeSystem('32.0G', '6.5G'));
    expect(s).not.toBeNull();
    expect(s?.limitedBy).toBe('datastore');
    expect(s?.effectiveFree).toBe('6.5G');
    expect(s?.datastorePool).toBe('364.5G');
    expect(s?.datastorePath).toBe('/mnt/rediacc');
  });

  it('reports disk as the limiting resource when it has less free space', () => {
    const s = deriveStorageSummary(makeSystem('4.0G', '200.0G'));
    expect(s?.limitedBy).toBe('disk');
    expect(s?.effectiveFree).toBe('4.0G');
  });

  it('omits the recommendation when effective free is >= 10G', () => {
    expect(deriveStorageSummary(makeSystem('50.0G', '20.0G'))?.recommendation).toBeNull();
  });

  it('recommends a resize when effective free is < 10G', () => {
    expect(deriveStorageSummary(makeSystem('50.0G', '6.5G'))?.recommendation).toBe(
      'Low storage. Expand with: rdc datastore resize'
    );
  });
});

describe('collectSections', () => {
  it('appends system when a subset omitting it is requested', () => {
    const sections = collectSections({ repositories: true });
    expect(sections).toContain('repositories');
    expect(sections).toContain('system');
  });

  it('does not duplicate system when it is already requested', () => {
    const sections = collectSections({ system: true, repositories: true });
    expect(sections.filter((s) => s === 'system')).toHaveLength(1);
  });

  it('returns an empty list when no sections are requested (full query)', () => {
    expect(collectSections({})).toEqual([]);
  });
});

const GUID_A = 'aaaaaaaa-0000-0000-0000-000000000001';
const GUID_B = 'bbbbbbbb-0000-0000-0000-000000000002';

function makeStorageHealth(): StorageHealthResult {
  return {
    repositories: [
      {
        name: 'gitlab',
        guid: GUID_A,
        size: 2 * 1024 ** 3, // 2 GiB
        size_human: '13.7 GB',
        exclusive: 910.3 * 1024 ** 2,
        exclusive_human: '910.3 MB',
        shared: 12.8 * 1024 ** 3,
        shared_human: '12.8 GB',
        divergence_percent: 6.42,
        extents: 300, // 300 / 2GiB = 150/GB
        fragmentation: 'moderate',
        quota_bytes: 16 * 1024 ** 3,
        allocated_bytes: 13.7 * 1024 ** 3,
        mounted: true,
        discards_enabled: true,
        reclaimable_human: '7.7 GB',
      },
      {
        name: 'demo-stackoverflow:kopya1',
        guid: GUID_B,
        size: 128 * 1024 ** 3,
        size_human: '128.0 GB',
        exclusive: 97.8 * 1024 ** 2,
        exclusive_human: '97.8 MB',
        shared: 127.9 * 1024 ** 3,
        shared_human: '127.9 GB',
        divergence_percent: 0.1,
        extents: 6400,
        fragmentation: 'low',
        quota_bytes: 256 * 1024 ** 3,
        allocated_bytes: 128 * 1024 ** 3,
        // The sealed volume: NOT mounted, so status.ts's `!sh.mounted` branch prints '-'
        // for both mounted-only columns. The fixture used to express this by omitting the
        // field, which `RepositoryStorageHealth` does not permit -- it declares
        // `mounted: boolean`. Only the `as unknown as` cast let that stand.
        mounted: false,
        discards_enabled: false,
      },
    ],
    savings_human: 'Unique: 2.3 GB | Shared: 656.2 GB | Efficiency: 99.6%',
    savings_bytes: 656.2 * 1024 ** 3,
    scan_duration_ms: 412,
    total_repos: 2,
    total_size: 130 * 1024 ** 3,
    total_exclusive: 910.3 * 1024 ** 2 + 97.8 * 1024 ** 2,
    total_shared: 12.8 * 1024 ** 3 + 127.9 * 1024 ** 3,
  } satisfies StorageHealthResult;
}

describe('buildStorageHealthRows', () => {
  it('returns an empty array when storage-health data is absent', () => {
    const resolve = createRepoNameResolver({});
    expect(buildStorageHealthRows(undefined, resolve)).toEqual([]);
    expect(
      buildStorageHealthRows(
        {
          repositories: [],
          savings_bytes: 0,
          savings_human: '',
          scan_duration_ms: 0,
          total_exclusive: 0,
          total_repos: 0,
          total_shared: 0,
          total_size: 0,
        },
        resolve
      )
    ).toEqual([]);
  });

  it('passes pre-formatted *_human fields through and formats divergence', () => {
    const resolve = createRepoNameResolver({ [GUID_A]: 'gitlab:latest' });
    const rows = buildStorageHealthRows(makeStorageHealth(), resolve);
    expect(rows[0]).toEqual({
      name: 'gitlab',
      quota: '16.0 GB',
      allocated: '13.7 GB',
      exclusive: '910.3 MB',
      shared: '12.8 GB',
      reclaimable: '7.7 GB',
      discards: 'on',
      divergence: '6.4%',
      fragmentation: '150/GB',
    });
  });

  it('shows dashes for the mounted-only columns when a repo is unmounted', () => {
    const resolve = createRepoNameResolver({ [GUID_A]: 'gitlab:latest' });
    const rows = buildStorageHealthRows(makeStorageHealth(), resolve);
    // GUID_B is `mounted: false` in the fixture (a sealed volume).
    expect(rows[1].reclaimable).toBe('-');
    expect(rows[1].discards).toBe('-');
  });

  it("marks server-sourced names (resolved from renet, not local config) with ' *'", () => {
    // GUID_B is not in the local config map, so it resolves from the server name.
    const resolve = createRepoNameResolver({ [GUID_A]: 'gitlab:latest' });
    const rows = buildStorageHealthRows(makeStorageHealth(), resolve);
    expect(rows[1].name).toBe('demo-stackoverflow:kopya1 *');
  });
});

describe('fragmentationPerGb', () => {
  it('reports extents per GB', () => {
    expect(fragmentationPerGb(300, 2 * 1024 ** 3)).toBe('150/GB');
    expect(fragmentationPerGb(0, 8 * 1024 ** 3)).toBe('0/GB');
  });

  it('falls back to the raw extent count when size is unknown', () => {
    expect(fragmentationPerGb(420, 0)).toBe('420');
  });
});

describe('table/JSON section parity guard', () => {
  // Every data-bearing ListResult section must be classified: either rendered as
  // a table section, or explicitly JSON-only (a conscious decision). This object
  // is typed `Record<keyof ListResult, ...>` so that adding a section to
  // ListResult forces a decision here.
  //
  // CAVEAT, verified 2026-07-18: that enforcement does NOT currently work.
  // packages/cli/tsconfig.json excludes `**/*.test.ts`, and `npm run typecheck`
  // is plain `tsc --noEmit` over that config, so this file is never typechecked
  // and a missing key cannot fail a build. Adding `backup_coverage` produced no
  // error until it was added by hand. Treat this list as a manual checklist
  // until tests are typechecked (e.g. vitest --typecheck or a test tsconfig).
  const SECTION_COVERAGE: Record<keyof ListResult, 'table' | 'json-only'> = {
    system: 'table',
    repositories: 'table',
    storage_health: 'table',
    containers: 'table',
    services: 'table',
    system_containers: 'table',
    network: 'table',
    block_devices: 'table',
    license_statuses: 'table',
    health_drift: 'table',
    backup_coverage: 'table',
  };

  it('renders storage_health in the table (the gap this change closes)', () => {
    expect(SECTION_COVERAGE.storage_health).toBe('table');
  });

  // health_drift used to be the one JSON-only section, visible only via
  // `--strict`. The watchdog maintains it to catch containers failing their
  // healthchecks for days; a signal you must already suspect to see is not a
  // signal. --strict still governs the exit code, but the data is now shown.
  it('leaves no section JSON-only', () => {
    const jsonOnly = Object.entries(SECTION_COVERAGE)
      .filter(([, mode]) => mode === 'json-only')
      .map(([key]) => key);
    expect(jsonOnly).toEqual([]);
  });
});
