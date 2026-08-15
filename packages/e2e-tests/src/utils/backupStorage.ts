/**
 * Assertions for the content-addressed chunk-store backup path, kept apart from
 * the suites that use them.
 *
 * Two reasons this is a module and not a block of `expect`s inside the spec:
 *
 *  1. The interesting claims are ARITHMETIC — a usage row that adds up, a
 *     manifest chain that links, an incremental that is bounded by the cells it
 *     touched. Arithmetic is worth checking with planted values, including the
 *     values a broken server would return, and a Playwright suite that needs a
 *     VM fleet can never do that.
 *  2. The suites that consume it are machine-gated. Without this split, every
 *     assertion in the wave would be dark on a developer box, which is the
 *     failure mode the whole testing spec is written against (the old backup
 *     suites "verify nothing": 17 tests asserting only that a command PARSED).
 *
 * Each function returns a list of VIOLATIONS rather than throwing, so a caller
 * reports all of them at once and the unit tests can assert on the exact text.
 */

/** GET /backups/usage — mirrors `backupUsageResponse` (account backup.dto.ts). */
export interface BackupUsage {
  subscriptionId: string;
  storedBytes: number;
  chunkCount: number;
  usageAdjustment: number;
  leasedBytes: number;
  activeLeases: number;
  usedBytes: number;
  quotaBytes: number;
  overLimit: boolean;
  retentionStartedAt: string | null;
  lineages: {
    lineageGuid: string;
    storedBytes: number;
    chunkCount: number;
    logicalBytes: number;
    updatedAt: string;
  }[];
}

/** GET /backups/manifests — mirrors `backupManifestsResponse`. */
export interface BackupManifest {
  snapshotId: string;
  lineageGuid: string;
  streamId: string;
  parentSnapshotId?: string | null;
  cellSizeBytes: number;
  totalBytes: number;
  addedBytes: number;
  addedChunkCount: number;
  createdAt: string;
}

/**
 * Everything that must hold about one usage response, whatever the numbers are.
 *
 * The quota is the only lever in this feature, so "the page renders" is not a
 * test: the row has to be internally consistent, or a user is being billed
 * against arithmetic nobody checked.
 */
export function usageViolations(usage: BackupUsage): string[] {
  return [...ledgerArithmeticViolations(usage), ...lineageBreakdownViolations(usage)];
}

/** The aggregate row: the sum, the flag, and the counters that back them. */
function ledgerArithmeticViolations(usage: BackupUsage): string[] {
  const bad: string[] = [];
  const expectedUsed = usage.storedBytes + usage.leasedBytes + usage.usageAdjustment;
  if (usage.usedBytes !== expectedUsed) {
    bad.push(
      `usedBytes ${usage.usedBytes} is not storedBytes + leasedBytes + usageAdjustment (${expectedUsed})`
    );
  }
  if (usage.overLimit !== usage.usedBytes > usage.quotaBytes) {
    bad.push(
      `overLimit is ${usage.overLimit} while usedBytes ${usage.usedBytes} vs quotaBytes ${usage.quotaBytes} says ${usage.usedBytes > usage.quotaBytes}`
    );
  }
  if (usage.quotaBytes <= 0) {
    bad.push(
      `quotaBytes is ${usage.quotaBytes}: every subscription has a quota, the free one included`
    );
  }
  for (const field of ['storedBytes', 'chunkCount', 'leasedBytes', 'activeLeases'] as const) {
    if (usage[field] < 0) bad.push(`${field} is negative (${usage[field]})`);
  }
  if (usage.storedBytes > 0 && usage.chunkCount === 0) {
    bad.push(`${usage.storedBytes} stored bytes across 0 chunks: the ledger disagrees with itself`);
  }
  return bad;
}

/** The per-repo rows, and their relationship to the aggregate. */
function lineageBreakdownViolations(usage: BackupUsage): string[] {
  const bad: string[] = [];
  let lineageStored = 0;
  for (const lineage of usage.lineages) {
    lineageStored += lineage.storedBytes;
    if (lineage.storedBytes < 0 || lineage.logicalBytes < 0) {
      bad.push(`lineage ${lineage.lineageGuid} reports negative bytes`);
    }
    // Physical unique bytes can never exceed the logical data they protect:
    // dedup and ZERO-cell elision only ever push the stored figure DOWN.
    if (lineage.storedBytes > lineage.logicalBytes) {
      bad.push(
        `lineage ${lineage.lineageGuid} stores ${lineage.storedBytes} bytes for ${lineage.logicalBytes} logical bytes`
      );
    }
  }
  // Object keys are per-lineage (t/<tenant>/l/<lineage>/c/<hash>), so there is
  // no cross-lineage sharing to make the parts exceed the whole.
  if (lineageStored > usage.storedBytes) {
    bad.push(
      `per-lineage stored bytes sum to ${lineageStored}, more than the aggregate ${usage.storedBytes}`
    );
  }
  return bad;
}

/**
 * Everything that must hold about a manifest index for ONE lineage.
 *
 * `expectSeedFirst` is what makes this falsifiable on a fresh lineage: the
 * oldest manifest must be a full seed (no parent), and every later one must
 * name a parent the index still holds — a chain with a dangling parent is a
 * restore that cannot be materialized.
 */
export function manifestChainViolations(manifests: BackupManifest[]): string[] {
  if (manifests.length === 0) return [];
  return [
    ...indexOrderingViolations(manifests),
    ...chainLinkageViolations(manifests),
    ...manifests.flatMap(perManifestViolations),
  ];
}

/** Ordering, uniqueness, and one geometry per lineage. */
function indexOrderingViolations(manifests: BackupManifest[]): string[] {
  const bad: string[] = [];
  // The route documents newest-first (createdAt desc).
  for (let i = 1; i < manifests.length; i++) {
    if (manifests[i - 1].createdAt < manifests[i].createdAt) {
      bad.push(
        `manifests are not newest-first: ${manifests[i - 1].snapshotId} (${manifests[i - 1].createdAt}) precedes ${manifests[i].snapshotId} (${manifests[i].createdAt})`
      );
    }
  }
  if (new Set(manifests.map((m) => m.snapshotId)).size !== manifests.length) {
    bad.push('the index repeats a snapshot id; commit is meant to be idempotent by snapshot id');
  }
  const cellSizes = new Set(manifests.map((m) => m.cellSizeBytes));
  if (cellSizes.size > 1) {
    bad.push(
      `the lineage mixes cell sizes (${[...cellSizes].join(', ')}); geometry is fixed until an explicit re-seed`
    );
  }
  return bad;
}

/** Every delta must reach a full seed, or it cannot be materialized. */
function chainLinkageViolations(manifests: BackupManifest[]): string[] {
  const bad: string[] = [];
  const known = new Set(manifests.map((m) => m.snapshotId));
  const oldest = manifests[manifests.length - 1];
  if (oldest.parentSnapshotId) {
    bad.push(
      `the oldest manifest ${oldest.snapshotId} names parent ${oldest.parentSnapshotId}, which the index does not hold`
    );
  }
  for (const m of manifests) {
    if (m.parentSnapshotId && !known.has(m.parentSnapshotId)) {
      bad.push(`${m.snapshotId} names a parent the index does not hold: ${m.parentSnapshotId}`);
    }
  }
  return bad;
}

/** What must hold about one manifest row on its own. */
function perManifestViolations(m: BackupManifest): string[] {
  const bad: string[] = [];
  if (m.addedBytes > m.totalBytes) {
    bad.push(`${m.snapshotId} added ${m.addedBytes} bytes to a snapshot of ${m.totalBytes}`);
  }
  if (m.addedBytes > 0 && m.addedChunkCount === 0) {
    bad.push(`${m.snapshotId} added ${m.addedBytes} bytes in 0 chunks`);
  }
  if (m.cellSizeBytes <= 0) bad.push(`${m.snapshotId} records a cell size of ${m.cellSizeBytes}`);
  return bad;
}

/**
 * How many grid cells a write of `length` bytes at `offset` touches.
 *
 * The TypeScript twin of chunkstore's `TouchedCells` for ONE contiguous range,
 * and the reason an incremental upload can be bounded rather than merely
 * "smaller than the seed": a 1-byte write costs one cell, and a write straddling
 * a boundary costs two.
 */
export function touchedCellCount(offset: number, length: number, cellSizeBytes: number): number {
  if (length <= 0 || cellSizeBytes <= 0) return 0;
  const first = Math.floor(offset / cellSizeBytes);
  const last = Math.floor((offset + length - 1) / cellSizeBytes);
  return last - first + 1;
}

/**
 * What an incremental run is allowed to have uploaded after a known write.
 *
 * Upper bound: the cells the write touched, whole (the store addresses cells,
 * not byte ranges), PLUS `filesystemMetadataCells`. Lower bound: something — an
 * incremental that uploads NOTHING after a real write is the silent-data-loss
 * direction, and it is the one a "smaller than the seed" assertion would
 * happily accept.
 *
 * ## Why the metadata allowance exists, measured rather than guessed
 *
 * The offset/length pair describes a write into a FILESYSTEM, but the cells are
 * counted on the ENCRYPTED IMAGE underneath it. A 4 KiB file write does not
 * dirty 4 KiB of image: ext4 also touches its journal, the group descriptors,
 * the inode table and the block bitmap, and those live at fixed offsets far
 * from the data block. Measured live on 2026-08-15 (1 GiB ext4-in-LUKS repo,
 * 4 MiB cells, a single 4 KiB `dd`): 5 cells, 20 MiB, where the data block
 * alone accounts for 1. The a-priori "one touched cell" bound is therefore
 * arithmetic about a raw image that no suite can actually produce — the image
 * is LUKS-encrypted, so a raw write at a known offset would corrupt it.
 *
 * Defaulting the allowance to 0 keeps the pure cell arithmetic exact for
 * callers that plant image-level numbers (the unit tests do), while a live
 * suite states the allowance it measured. The bound stays FALSIFIABLE either
 * way: a full re-upload of the same repo is 19+ cells and fails at any
 * allowance a small write can justify.
 */
export function incrementalViolations(input: {
  seed: BackupManifest;
  incremental: BackupManifest;
  writeOffset: number;
  writeLength: number;
  /** Extra whole cells a real filesystem may dirty for its own bookkeeping. */
  filesystemMetadataCells?: number;
}): string[] {
  const bad: string[] = [];
  const { seed, incremental, writeOffset, writeLength } = input;
  const metadataCells = Math.max(0, input.filesystemMetadataCells ?? 0);
  const cell = incremental.cellSizeBytes;

  if (incremental.parentSnapshotId !== seed.snapshotId) {
    bad.push(
      `the incremental names parent ${incremental.parentSnapshotId ?? '(none)'}, want the seed ${seed.snapshotId}`
    );
  }
  if (incremental.addedBytes === 0) {
    bad.push('the incremental uploaded nothing after a real write: the changed cells were dropped');
  }
  const maxAllowed = (touchedCellCount(writeOffset, writeLength, cell) + metadataCells) * cell;
  if (incremental.addedBytes > maxAllowed) {
    bad.push(
      `the incremental uploaded ${incremental.addedBytes} bytes for a ${writeLength}-byte write, ` +
        `over the ${maxAllowed}-byte cell bound: it is not sending only changed cells`
    );
  }
  if (incremental.totalBytes !== seed.totalBytes) {
    bad.push(
      `the snapshot size changed from ${seed.totalBytes} to ${incremental.totalBytes} without a resize`
    );
  }
  return bad;
}

/**
 * Does a `--help` listing register this verb as a subcommand?
 *
 * A LIVE probe, not a version guess: a tier that needs a verb turns itself on
 * the moment the binary grows it, and cannot be declared away once it exists
 * (`resolvePrerequisites` only honours a declaration when something is
 * genuinely missing).
 *
 * `verb` is the full argv path (`backup snapshot`), while `helpOutput` is the
 * help of its PARENT (`renet backup --help`), which lists only the children.
 * So the token checked is the one FOLLOWING the parent, not the first token —
 * the first token is the parent itself and never appears in its own child
 * list. Getting that backwards makes the probe answer "absent" for a verb that
 * is right there, which is how this function first behaved and what running it
 * against the real binary caught.
 */
export function verbIsRegistered(helpOutput: string, verb: string, parent = 'backup'): boolean {
  const tokens = verb.trim().split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return false;
  const parentIndex = tokens.indexOf(parent);
  const child = parentIndex >= 0 ? tokens[parentIndex + 1] : tokens[0];
  if (!child) return false;
  // Cobra/commander list subcommands one per line, indented, name first.
  // Anchoring to the line start avoids counting a mention inside a
  // description or an example.
  const escaped = child.replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^\\s+${escaped}(\\s|$)`, 'm').test(helpOutput);
}

/**
 * The argv of the chunk-store run and restore verbs.
 *
 * `run` is FACT as of 2026-08-14: `renet backup snapshot` is registered, and
 * its flags are `--datastore --repo --cell-bytes --parallelism --bwlimit
 * --dry-run --reseed` (verified against the BUILT binary, not the source).
 *
 * `restore` is FACT as of 2026-08-14 and no longer defaults to empty: the
 * download path landed (`renet backup restore`, `pkg/chunkstore/download.go`
 * plus `restore.go`), and its flags are `--repo --datastore --lineage --at
 * --parallelism --bwlimit --dry-run`, read off the BUILT binary rather than the
 * source. It previously had no default on purpose, because an invented one
 * would have let the tier light up and then fail on an unknown command,
 * blaming the restore for a verb nobody had written.
 *
 * Defaulting it does NOT make the tier trust an env var: the tier still probes
 * `renet backup --help` against the deployed binary and re-runs that probe on
 * the machine, so a fleet that cannot run the verb still skips loudly. That
 * probe is the evidence; this string is only the argv to use once it passes.
 */
const CHUNK_VERB_ENV = {
  run: 'E2E_CHUNK_BACKUP_VERB',
  restore: 'E2E_CHUNK_RESTORE_VERB',
} as const;

export function chunkVerbs(env: NodeJS.ProcessEnv = process.env): { run: string; restore: string } {
  return {
    run: (env[CHUNK_VERB_ENV.run] ?? 'backup snapshot').trim(),
    restore: (env[CHUNK_VERB_ENV.restore] ?? 'backup restore').trim(),
  };
}

/** One NDJSON record of `renet backup snapshot` (cmd/renet/backup_snapshot.go:34). */
export interface SnapshotRecord {
  guid: string;
  status: 'stored' | 'skipped' | 'quota-refused' | 'failed';
  reason?: string;
  snapshotId?: string;
  parentSnapshotId?: string;
  lineage?: string;
  streamId?: string;
  cellBytes?: number;
  imageBytes?: number;
  rehashReason?: string;
  chunksAsked: number;
  chunksMissing: number;
  chunksUploaded: number;
  bytesUploaded: number;
  grantsMinted: number;
  resumed: boolean;
  durationMs: number;
}

/** The four statuses the verb defines; anything else is a contract break. */
const SNAPSHOT_STATUSES = new Set(['stored', 'skipped', 'quota-refused', 'failed']);

/**
 * What must hold about one snapshot record, whatever it reports.
 *
 * The counts are a funnel — asked >= missing >= uploaded — and every
 * non-success status has to carry a reason. Both matter more than they look:
 * this record IS the machine's report of whether a backup happened, and a
 * record claiming "stored" while naming no snapshot is the exact shape a silent
 * no-op takes.
 */
export function snapshotRecordViolations(record: SnapshotRecord): string[] {
  return [...recordStatusViolations(record), ...recordCountViolations(record)];
}

/** The status field and what it obliges the rest of the record to say. */
function recordStatusViolations(record: SnapshotRecord): string[] {
  const bad: string[] = [];
  if (!SNAPSHOT_STATUSES.has(record.status)) {
    bad.push(`unknown status ${JSON.stringify(record.status)}`);
  }
  if (record.status !== 'stored' && !record.reason) {
    bad.push(`status ${record.status} carries no reason`);
  }
  if (record.status === 'stored' && !record.snapshotId) {
    bad.push('a stored snapshot with no snapshot id');
  }
  return bad;
}

/** The counts, which are a funnel: asked >= missing >= uploaded. */
function recordCountViolations(record: SnapshotRecord): string[] {
  const bad: string[] = [];
  if (record.chunksMissing > record.chunksAsked) {
    bad.push(`missing ${record.chunksMissing} of ${record.chunksAsked} asked`);
  }
  if (record.chunksUploaded > record.chunksMissing) {
    bad.push(`uploaded ${record.chunksUploaded} of ${record.chunksMissing} missing`);
  }
  for (const field of [
    'chunksAsked',
    'chunksMissing',
    'chunksUploaded',
    'bytesUploaded',
  ] as const) {
    if (record[field] < 0) bad.push(`${field} is negative (${record[field]})`);
  }
  if (record.chunksUploaded > 0 && record.bytesUploaded === 0) {
    bad.push(`${record.chunksUploaded} chunks uploaded in 0 bytes`);
  }
  if (record.bytesUploaded > 0 && record.grantsMinted === 0) {
    bad.push('bytes moved without a grant ever being minted');
  }
  return bad;
}

/**
 * Extra invariants for a `--dry-run` record. The flag's whole promise is "no
 * session, no grant, no upload", so anything that moved is the flag not being
 * honoured — on a run the operator was told would cost nothing.
 */
export function dryRunViolations(record: SnapshotRecord): string[] {
  const bad = snapshotRecordViolations(record);
  if (record.chunksUploaded !== 0) bad.push(`dry run uploaded ${record.chunksUploaded} chunks`);
  if (record.bytesUploaded !== 0) bad.push(`dry run moved ${record.bytesUploaded} bytes`);
  if (record.grantsMinted !== 0) bad.push(`dry run minted ${record.grantsMinted} grant(s)`);
  if (record.streamId) bad.push(`dry run resolved a stream id (${record.streamId})`);
  return bad;
}
