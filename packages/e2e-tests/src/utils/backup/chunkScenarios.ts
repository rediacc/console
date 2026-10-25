/**
 * Pure helpers for the suite 26 scenario cases (plan boxes K2 to K7, K11, L5): the verdicts the
 * cases assert are computed here, from plain data, so they are unit-testable without a fleet.
 */
import type { BackupManifest } from '../backupStorage';

/** The slice of the restore verb's stdout record the scenario cases read. */
export interface RestoreRecord {
  status: string;
  snapshotId?: string;
  chunksWanted: number;
  chunksFetched: number;
  chunksReused: number;
  resumed: boolean;
  seed?: string;
  seedGuid?: string;
  reason?: string;
}

/** One stdout line as a restore record, or undefined for any other line. */
export function parseRestoreRecord(line: string): RestoreRecord | undefined {
  const trimmed = line.trim();
  if (!trimmed.startsWith('{') || !trimmed.includes('"chunksWanted"')) return undefined;
  try {
    return JSON.parse(trimmed) as RestoreRecord;
  } catch {
    return undefined;
  }
}

/** Every restore record in a stdout capture, in order. */
export function restoreRecordsOf(stdout: string): RestoreRecord[] {
  return stdout.split('\n').flatMap((line) => {
    const record = parseRestoreRecord(line);
    return record ? [record] : [];
  });
}

/** The systemd service a `backup schedule` push installs for a strategy (K7). */
export function scheduleServiceUnit(strategy: string): string {
  return `rediacc-backup-${strategy}.service`;
}

/**
 * A restore mints a fresh repository identity (plan box E1): the restored GUID is a real UUID and
 * is neither the source's nor any GUID the config already held.
 */
export function newGuidViolations(
  sourceGuid: string,
  restoredGuid: string,
  otherKnownGuids: readonly string[] = []
): string[] {
  const bad: string[] = [];
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(restoredGuid)) {
    bad.push(`the restored repository has no valid GUID (${JSON.stringify(restoredGuid)})`);
  }
  if (restoredGuid === sourceGuid) {
    bad.push(`the restore reused the source GUID ${sourceGuid}; it must mint a new one`);
  }
  if (otherKnownGuids.includes(restoredGuid)) {
    bad.push(`the restored GUID ${restoredGuid} collides with another repository in the config`);
  }
  return bad;
}

/**
 * The counter log a cold backup restores (K6). Every line is one whole decimal integer and each
 * is exactly one above the last, so a gap, a repeat or a torn (partial) line each fail by name.
 * The file must end in a newline: a final line without one is a write cut mid-way.
 */
export function counterLogViolations(text: string, minimumLines = 1): string[] {
  const bad: string[] = [];
  if (text.length > 0 && !text.endsWith('\n')) {
    bad.push('the log ends mid-line: the last write is torn');
  }
  const lines = text.split('\n').filter((l, i, all) => i < all.length - 1 || l !== '');
  let previous: number | undefined;
  lines.forEach((line, index) => {
    if (!/^\d+$/.test(line)) {
      bad.push(`line ${index + 1} is not a whole counter value: ${JSON.stringify(line)}`);
      return;
    }
    const value = Number(line);
    if (previous !== undefined && value !== previous + 1) {
      bad.push(`counter jumps from ${previous} to ${value} at line ${index + 1}`);
    }
    previous = value;
  });
  if (lines.length < minimumLines) {
    bad.push(
      `the log holds ${lines.length} lines, fewer than the ${minimumLines} written before the backup`
    );
  }
  return bad;
}

/**
 * After a retention sweep over a lineage with several streams (K3): each stream keeps at least
 * `min(floor, before)` manifests including its newest, and every kept delta's parent is still in
 * the index, so every chain resolves. The manifest lists are newest-first, as the index returns them.
 */
export function retentionSweepViolations(
  before: readonly BackupManifest[],
  after: readonly BackupManifest[],
  floor: number
): string[] {
  const bad: string[] = [];
  const kept = new Set(after.map((m) => m.snapshotId));
  const byStream = (list: readonly BackupManifest[]): Map<string, BackupManifest[]> => {
    const map = new Map<string, BackupManifest[]>();
    for (const m of list) map.set(m.streamId, [...(map.get(m.streamId) ?? []), m]);
    return map;
  };
  const afterStreams = byStream(after);
  for (const [streamId, was] of byStream(before)) {
    const now = afterStreams.get(streamId) ?? [];
    const required = Math.min(floor, was.length);
    if (now.length < required) {
      bad.push(
        `stream ${streamId} keeps ${now.length} of ${was.length}, below its floor of ${required}`
      );
    }
    const newest = [...was].sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
    if (newest && !kept.has(newest.snapshotId)) {
      bad.push(`stream ${streamId} lost its newest manifest ${newest.snapshotId}`);
    }
  }
  bad.push(...danglingParents(after));
  return bad;
}

/** Manifests whose parent is not in the same list: a chain that no longer resolves. */
function danglingParents(manifests: readonly BackupManifest[]): string[] {
  const ids = new Set(manifests.map((m) => m.snapshotId));
  return manifests
    .filter((m) => m.parentSnapshotId && !ids.has(m.parentSnapshotId))
    .map((m) => `manifest ${m.snapshotId} names a parent ${m.parentSnapshotId} the sweep deleted`);
}

/** Distinct stream ids across manifests: K3 needs several to prove anything about a floor per stream. */
export function distinctStreams(manifests: readonly BackupManifest[]): string[] {
  return [...new Set(manifests.map((m) => m.streamId))];
}

/**
 * A restore that seeded from a local copy (L5) reports its seed kind and fetches fewer chunks than
 * it wanted, because the seed's cells were reused instead of downloaded.
 */
export function seededRestoreViolations(
  record: RestoreRecord,
  expectedSeedGuid?: string
): string[] {
  const bad: string[] = [];
  if (record.status !== 'restored')
    bad.push(`restore status is ${record.status}: ${record.reason ?? ''}`);
  if (!record.seed)
    bad.push('the restore used no seed although a local copy of the lineage exists');
  if (expectedSeedGuid && record.seedGuid !== expectedSeedGuid) {
    bad.push(`seeded from ${record.seedGuid ?? 'nothing'}, expected ${expectedSeedGuid}`);
  }
  if (record.chunksReused <= 0) bad.push('the seed reused no cells');
  if (record.chunksFetched >= record.chunksWanted) {
    bad.push(
      `fetched ${record.chunksFetched} of ${record.chunksWanted} wanted chunks; a seed must lower that`
    );
  }
  return bad;
}
