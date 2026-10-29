/**
 * The prune preview lists the staging a killed `backup pull` strands (repositories/.<guid>) as a
 * `pull-staging` row, read from renet's `stale_backup_pull_staging` key (PLAN-backup-local-image
 * R2). It is not the retired `.pull-*` class, whose `stale_pull_staging` key renet no longer emits.
 */

import { describe, expect, it } from 'vitest';
import {
  buildPrunePreviewRows,
  countPrunedResources,
  type DatastorePrunableResources,
  parseDatastorePruneOutput,
} from '../datastore-prune-parser.js';

const GUID = 'bbbbbbbb-1111-2222-3333-444444444444';

describe('prune preview pull staging', () => {
  it('emits a pull-staging row for each abandoned pull staging', () => {
    const parsed = parseDatastorePruneOutput(
      JSON.stringify({ stale_backup_pull_staging: [`.${GUID}`], stale_locks: null })
    ) as DatastorePrunableResources;
    expect(buildPrunePreviewRows(parsed)).toEqual([{ type: 'pull-staging', resource: `.${GUID}` }]);
  });

  it('counts pruned pull staging in the real-run total', () => {
    expect(countPrunedResources({ backup_pull_staging_pruned: 2, locks_pruned: 1 })).toBe(3);
  });

  it('control: an empty or null class adds no row', () => {
    expect(buildPrunePreviewRows({ stale_backup_pull_staging: null })).toEqual([]);
    expect(buildPrunePreviewRows({})).toEqual([]);
  });
});
