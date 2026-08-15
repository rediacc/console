import { describe, expect, it } from 'vitest';
import {
  type BackupManifest,
  type BackupUsage,
  chunkVerbs,
  incrementalViolations,
  dryRunViolations,
  manifestChainViolations,
  type SnapshotRecord,
  snapshotRecordViolations,
  touchedCellCount,
  usageViolations,
  verbIsRegistered,
} from '../backupStorage';

/**
 * Every case here plants the numbers a BROKEN server would return, because an
 * assertion module tested only against healthy input is decoration: it would
 * pass on the day the ledger stops adding up, which is the only day it matters.
 */

const healthyUsage = (over: Partial<BackupUsage> = {}): BackupUsage => ({
  subscriptionId: 'sub-1',
  storedBytes: 900,
  chunkCount: 3,
  usageAdjustment: 0,
  leasedBytes: 100,
  activeLeases: 1,
  usedBytes: 1000,
  quotaBytes: 10_737_418_240,
  overLimit: false,
  retentionStartedAt: null,
  lineages: [
    {
      lineageGuid: 'lin-1',
      storedBytes: 900,
      chunkCount: 3,
      logicalBytes: 4096,
      updatedAt: '2026-08-14T10:00:00Z',
    },
  ],
  ...over,
});

describe('usageViolations', () => {
  it('accepts a consistent row', () => {
    expect(usageViolations(healthyUsage())).toEqual([]);
  });

  it('catches usedBytes that is not the sum of its parts', () => {
    const bad = usageViolations(healthyUsage({ usedBytes: 999 }));
    expect(bad.join('\n')).toContain('is not storedBytes + leasedBytes + usageAdjustment');
  });

  it('honours a negative usage adjustment rather than assuming stored + leased', () => {
    // The adjustment column exists to correct the ledger in BOTH directions;
    // a checker that ignored its sign would reject a legitimately credited row.
    expect(usageViolations(healthyUsage({ usageAdjustment: -400, usedBytes: 600 }))).toEqual([]);
  });

  it('catches overLimit disagreeing with the quota arithmetic, in both directions', () => {
    const falseNegative = usageViolations(
      healthyUsage({ usedBytes: 2000, storedBytes: 1900, quotaBytes: 1000, overLimit: false })
    );
    expect(falseNegative.join('\n')).toContain('overLimit is false');

    const falsePositive = usageViolations(healthyUsage({ overLimit: true }));
    expect(falsePositive.join('\n')).toContain('overLimit is true');
  });

  it('treats usage exactly AT the quota as not over it', () => {
    // The boundary the flag is defined on. Without this row, a check written
    // with >= instead of > passes every other case here: `usedBytes` only ever
    // lands exactly on the quota when a subscription fills it precisely, which
    // is also the moment a wrong comparison starts refusing legitimate writes.
    const atLimit = healthyUsage({ quotaBytes: 1000, storedBytes: 900, overLimit: false });
    expect(atLimit.usedBytes).toBe(atLimit.quotaBytes);
    expect(usageViolations(atLimit)).toEqual([]);
    // ...and one byte past it is over.
    expect(
      usageViolations(healthyUsage({ quotaBytes: 999, storedBytes: 900, overLimit: false })).join(
        '\n'
      )
    ).toContain('overLimit is false');
  });

  it('catches a missing quota, negative counters, and bytes stored in zero chunks', () => {
    expect(usageViolations(healthyUsage({ quotaBytes: 0 })).join('\n')).toContain(
      'every subscription has a quota'
    );
    expect(usageViolations(healthyUsage({ leasedBytes: -1, usedBytes: 899 })).join('\n')).toContain(
      'leasedBytes is negative'
    );
    expect(usageViolations(healthyUsage({ chunkCount: 0 })).join('\n')).toContain(
      'the ledger disagrees with itself'
    );
  });

  it('catches a lineage storing more bytes than it protects, and parts exceeding the whole', () => {
    const inflated = healthyUsage();
    inflated.lineages[0].logicalBytes = 100;
    expect(usageViolations(inflated).join('\n')).toContain('logical bytes');

    const overSum = healthyUsage();
    overSum.lineages.push({ ...overSum.lineages[0], lineageGuid: 'lin-2' });
    expect(usageViolations(overSum).join('\n')).toContain('more than the aggregate');
  });
});

const seed: BackupManifest = {
  snapshotId: '20260814T100000Z-aaaa',
  lineageGuid: 'lin-1',
  streamId: 'stream-1',
  parentSnapshotId: null,
  cellSizeBytes: 1 << 20,
  totalBytes: 64 << 20,
  addedBytes: 32 << 20,
  addedChunkCount: 32,
  createdAt: '2026-08-14T10:00:00Z',
};

const incremental: BackupManifest = {
  ...seed,
  snapshotId: '20260814T110000Z-bbbb',
  parentSnapshotId: seed.snapshotId,
  addedBytes: 1 << 20,
  addedChunkCount: 1,
  createdAt: '2026-08-14T11:00:00Z',
};

describe('manifestChainViolations', () => {
  it('accepts an empty index and a healthy newest-first chain', () => {
    expect(manifestChainViolations([])).toEqual([]);
    expect(manifestChainViolations([incremental, seed])).toEqual([]);
  });

  it('catches an index that is not newest-first', () => {
    expect(manifestChainViolations([seed, incremental]).join('\n')).toContain('not newest-first');
  });

  it('catches a dangling parent — a snapshot that cannot be materialized', () => {
    const orphan = { ...incremental, parentSnapshotId: 'gone-forever' };
    expect(manifestChainViolations([orphan, seed]).join('\n')).toContain(
      'names a parent the index does not hold'
    );
  });

  it('catches an oldest manifest that is not a full seed', () => {
    const noSeed = { ...seed, parentSnapshotId: 'older-than-history' };
    expect(manifestChainViolations([noSeed]).join('\n')).toContain('which the index does not hold');
  });

  it('catches a repeated snapshot id (commit is idempotent by snapshot id)', () => {
    expect(manifestChainViolations([incremental, incremental]).join('\n')).toContain(
      'repeats a snapshot id'
    );
  });

  it('catches mixed cell sizes within one lineage', () => {
    const regridded = { ...incremental, cellSizeBytes: 4 << 20 };
    expect(manifestChainViolations([regridded, seed]).join('\n')).toContain('mixes cell sizes');
  });

  it('catches added bytes exceeding the snapshot, and bytes added in zero chunks', () => {
    expect(
      manifestChainViolations([{ ...seed, addedBytes: seed.totalBytes + 1 }]).join('\n')
    ).toContain('added');
    expect(manifestChainViolations([{ ...seed, addedChunkCount: 0 }]).join('\n')).toContain(
      'in 0 chunks'
    );
  });
});

describe('touchedCellCount', () => {
  it('charges one cell for a write inside a cell and two for a straddling write', () => {
    expect(touchedCellCount(0, 1, 1024)).toBe(1);
    expect(touchedCellCount(1023, 2, 1024)).toBe(2);
    expect(touchedCellCount(0, 1024, 1024)).toBe(1); // ends exactly on the boundary
    expect(touchedCellCount(1024, 1, 1024)).toBe(1); // starts exactly on it
    expect(touchedCellCount(0, 4096, 1024)).toBe(4);
    expect(touchedCellCount(0, 0, 1024)).toBe(0);
  });
});

describe('incrementalViolations', () => {
  const write = { writeOffset: 8 << 20, writeLength: 4096 };

  it('accepts an incremental bounded by the cell it touched', () => {
    expect(incrementalViolations({ seed, incremental, ...write })).toEqual([]);
  });

  it('catches an incremental that uploaded nothing after a real write', () => {
    const silent = { ...incremental, addedBytes: 0, addedChunkCount: 0 };
    expect(incrementalViolations({ seed, incremental: silent, ...write }).join('\n')).toContain(
      'uploaded nothing after a real write'
    );
  });

  it('catches a full re-upload dressed up as an incremental', () => {
    // The failure this whole tier exists to catch: the run "succeeds", the
    // manifest chain looks right, and every cell was sent again.
    const wasteful = { ...incremental, addedBytes: 32 << 20, addedChunkCount: 32 };
    expect(incrementalViolations({ seed, incremental: wasteful, ...write }).join('\n')).toContain(
      'it is not sending only changed cells'
    );
  });

  it('allows exactly two cells for a write that straddles a cell boundary', () => {
    const straddle = { writeOffset: (8 << 20) - 1, writeLength: 2 };
    const twoCells = { ...incremental, addedBytes: 2 << 20, addedChunkCount: 2 };
    expect(incrementalViolations({ seed, incremental: twoCells, ...straddle })).toEqual([]);
    // ...and not three.
    const threeCells = { ...incremental, addedBytes: 3 << 20, addedChunkCount: 3 };
    expect(
      incrementalViolations({ seed, incremental: threeCells, ...straddle }).join('\n')
    ).toContain('over the');
  });

  it('widens the bound by the metadata cells a filesystem write dirties, and no further', () => {
    // The live suite writes through ext4-inside-LUKS, so a 4 KiB file write
    // also moves the journal and the group metadata: measured 5 cells for one
    // `dd`. The allowance has to admit that WITHOUT admitting a re-upload.
    const fiveCells = { ...incremental, addedBytes: 5 << 20, addedChunkCount: 5 };
    expect(
      incrementalViolations({ seed, incremental: fiveCells, ...write }).join('\n'),
      'without an allowance, five cells must still be over the one-cell bound'
    ).toContain('over the');
    expect(
      incrementalViolations({
        seed,
        incremental: fiveCells,
        ...write,
        filesystemMetadataCells: 8,
      })
    ).toEqual([]);
    // ...and the widened bound is still a bound: a full re-upload fails it.
    const wasteful = { ...incremental, addedBytes: 32 << 20, addedChunkCount: 32 };
    expect(
      incrementalViolations({
        seed,
        incremental: wasteful,
        ...write,
        filesystemMetadataCells: 8,
      }).join('\n')
    ).toContain('it is not sending only changed cells');
  });

  it('catches a broken parent link and a silent resize', () => {
    expect(
      incrementalViolations({
        seed,
        incremental: { ...incremental, parentSnapshotId: null },
        ...write,
      }).join('\n')
    ).toContain('want the seed');
    expect(
      incrementalViolations({
        seed,
        incremental: { ...incremental, totalBytes: seed.totalBytes * 2 },
        ...write,
      }).join('\n')
    ).toContain('without a resize');
  });
});

describe('verbIsRegistered', () => {
  // Shaped like the real `renet backup --help` (verified against the built
  // binary): the parent's own name never appears, the children are indented one
  // per line, and the prose above them mentions words that are NOT commands.
  const help = [
    'Manage repository backups with support for local and remote storage.',
    '- BTRFS snapshots for consistent backups',
    '',
    'Usage: renet backup [command]',
    '',
    'Available Commands:',
    '  list        List backups',
    '  push        Push a repository',
    '  snapshot    Upload a chunk-store snapshot of every repository',
    '  verify      Verify the anchor',
    '',
    'Run `renet backup chunk push` once the engine lands.',
  ].join('\n');

  it('finds a registered subcommand', () => {
    expect(verbIsRegistered(help, 'verify')).toBe(true);
    expect(verbIsRegistered(help, 'push --repo x')).toBe(true);
  });

  it('checks the token AFTER the parent, not the first token', () => {
    // The regression that only a live run caught. `renet backup --help` lists
    // the CHILDREN of `backup`, so there is no line reading "backup" in it.
    // A probe that tested the first token answered "absent" for a verb sitting
    // in the listing, and the tier that depended on it stayed dark after the
    // verb had landed.
    expect(help).not.toMatch(/^\s+backup(\s|$)/m);
    expect(verbIsRegistered(help, 'backup snapshot')).toBe(true);
    expect(verbIsRegistered(help, 'backup verify')).toBe(true);
    expect(verbIsRegistered(help, 'backup nonesuch')).toBe(false);
  });

  it('does not let a regex-special verb name change what is matched', () => {
    expect(verbIsRegistered(help, 'backup pu.h')).toBe(false);
  });

  it('does NOT count a verb that only appears inside prose', () => {
    // The instrument check: `chunk` appears in the help text, in a sentence.
    // A substring probe would report the engine as present and light a tier
    // that then fails eight assertions deep for the wrong reason.
    expect(help).toContain('chunk');
    expect(verbIsRegistered(help, 'chunk push')).toBe(false);
  });

  it('answers false for empty input', () => {
    expect(verbIsRegistered('', 'verify')).toBe(false);
    expect(verbIsRegistered(help, '   ')).toBe(false);
  });
});

describe('chunkVerbs', () => {
  it('defaults the run verb to the one renet actually registers', () => {
    expect(chunkVerbs({}).run).toBe('backup snapshot');
    expect(chunkVerbs({ E2E_CHUNK_BACKUP_VERB: 'backup run ' }).run).toBe('backup run');
  });

  it('defaults the restore verb to the one renet now registers', () => {
    // This used to assert '' — correct while renet had no download path, and
    // stale from the moment `renet backup restore` landed (2026-08-14) and the
    // module started defaulting it. The empty default existed so a
    // plausible-looking guess could not light the restore tier and then fail on
    // an unknown command; the tier's live `renet backup --help` probe is what
    // does that job now, so the default is argv, not a claim.
    expect(chunkVerbs({}).restore).toBe('backup restore');
    expect(chunkVerbs({ E2E_CHUNK_RESTORE_VERB: ' backup fetch ' }).restore).toBe('backup fetch');
  });
});

const storedRecord = (over: Partial<SnapshotRecord> = {}): SnapshotRecord => ({
  guid: '11111111-2222-3333-4444-555555555555',
  status: 'stored',
  snapshotId: '20260814T120000Z-0011223344556677',
  lineage: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
  cellBytes: 4 << 20,
  imageBytes: 64 << 20,
  chunksAsked: 16,
  chunksMissing: 4,
  chunksUploaded: 4,
  bytesUploaded: 16 << 20,
  grantsMinted: 1,
  resumed: false,
  durationMs: 1200,
  ...over,
});

describe('snapshotRecordViolations', () => {
  it('accepts a healthy stored record and a reasoned skip', () => {
    expect(snapshotRecordViolations(storedRecord())).toEqual([]);
    expect(
      snapshotRecordViolations(
        storedRecord({
          status: 'skipped',
          reason: 'merge in progress',
          chunksAsked: 0,
          chunksMissing: 0,
          chunksUploaded: 0,
          bytesUploaded: 0,
          grantsMinted: 0,
        })
      )
    ).toEqual([]);
  });

  it('catches a non-success status with no reason', () => {
    const silent = storedRecord({ status: 'failed', reason: undefined });
    expect(snapshotRecordViolations(silent).join('\n')).toContain('carries no reason');
  });

  it('catches a status the verb does not define', () => {
    const rogue = storedRecord({ status: 'ok' as SnapshotRecord['status'] });
    expect(snapshotRecordViolations(rogue).join('\n')).toContain('unknown status');
  });

  it('catches the counts flowing backwards through the funnel', () => {
    expect(snapshotRecordViolations(storedRecord({ chunksMissing: 20 })).join('\n')).toContain(
      'missing 20 of 16 asked'
    );
    expect(snapshotRecordViolations(storedRecord({ chunksUploaded: 9 })).join('\n')).toContain(
      'uploaded 9 of 4 missing'
    );
  });

  it('catches a stored snapshot with no id — the silent-no-op shape', () => {
    expect(snapshotRecordViolations(storedRecord({ snapshotId: undefined })).join('\n')).toContain(
      'stored snapshot with no snapshot id'
    );
  });

  it('catches chunks moved without bytes, and bytes moved without a grant', () => {
    expect(snapshotRecordViolations(storedRecord({ bytesUploaded: 0 })).join('\n')).toContain(
      'chunks uploaded in 0 bytes'
    );
    expect(snapshotRecordViolations(storedRecord({ grantsMinted: 0 })).join('\n')).toContain(
      'without a grant ever being minted'
    );
  });
});

describe('dryRunViolations', () => {
  const dry = storedRecord({
    chunksMissing: 0,
    chunksUploaded: 0,
    bytesUploaded: 0,
    grantsMinted: 0,
    streamId: undefined,
  });

  it('accepts a plan that moved nothing', () => {
    expect(dryRunViolations(dry)).toEqual([]);
  });

  it('catches a dry run that uploaded, minted, or resolved a stream', () => {
    // Each of these means "no session, no grant, no upload" was not true — on a
    // run the operator was told would cost nothing.
    expect(
      dryRunViolations({ ...dry, chunksUploaded: 1, chunksMissing: 1, bytesUploaded: 4096 }).join(
        '\n'
      )
    ).toContain('dry run uploaded 1 chunks');
    expect(dryRunViolations({ ...dry, grantsMinted: 1 }).join('\n')).toContain('minted 1 grant');
    expect(dryRunViolations({ ...dry, streamId: 'stream-7' }).join('\n')).toContain(
      'resolved a stream id'
    );
  });

  it('still enforces the plain record invariants', () => {
    expect(dryRunViolations({ ...dry, status: 'failed', reason: undefined }).join('\n')).toContain(
      'carries no reason'
    );
  });
});
