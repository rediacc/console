import { describe, expect, it } from 'vitest';
import {
  counterLogViolations,
  distinctStreams,
  newGuidViolations,
  parseRestoreRecord,
  restoreRecordsOf,
  retentionSweepViolations,
  scheduleServiceUnit,
  seededRestoreViolations,
} from '../backup/chunkScenarios';
import type { BackupManifest } from '../backupStorage';

const GUID_A = '11111111-1111-4111-8111-111111111111';
const GUID_B = '22222222-2222-4222-8222-222222222222';

const manifest = (id: string, stream: string, minute: number, parent?: string): BackupManifest => ({
  snapshotId: id,
  lineageGuid: 'L',
  streamId: stream,
  parentSnapshotId: parent ?? null,
  cellSizeBytes: 4,
  totalBytes: 4,
  addedBytes: 1,
  addedChunkCount: 1,
  createdAt: `2026-10-25T10:${String(minute).padStart(2, '0')}:00Z`,
});

describe('newGuidViolations', () => {
  it('accepts a fresh uuid', () => expect(newGuidViolations(GUID_A, GUID_B)).toEqual([]));
  it('refuses the source guid, a malformed one and a collision', () => {
    expect(newGuidViolations(GUID_A, GUID_A)).toHaveLength(1);
    expect(newGuidViolations(GUID_A, 'nope')).toHaveLength(1);
    expect(newGuidViolations(GUID_A, GUID_B, [GUID_B])).toHaveLength(1);
  });
});

describe('counterLogViolations', () => {
  it('accepts a consecutive log', () => expect(counterLogViolations('5\n6\n7\n', 3)).toEqual([]));
  it('names a gap, a torn tail, a garbage line and a short log', () => {
    expect(counterLogViolations('1\n2\n4\n')[0]).toContain('jumps from 2 to 4');
    expect(counterLogViolations('1\n2\n3')[0]).toContain('torn');
    expect(counterLogViolations('1\nx\n')[0]).toContain('not a whole counter');
    expect(counterLogViolations('1\n2\n', 5)[0]).toContain('fewer than');
  });
});

describe('retentionSweepViolations', () => {
  const before = [
    manifest('a4', 'A', 9, 'a3'),
    manifest('a3', 'A', 8, 'a2'),
    manifest('a2', 'A', 7, 'a1'),
    manifest('a1', 'A', 6),
    manifest('b2', 'B', 5, 'b1'),
    manifest('b1', 'B', 4),
  ];
  it('passes when each stream keeps its floor and chains resolve', () => {
    const after = [before[0], before[1], before[2], before[3], before[4], before[5]];
    expect(retentionSweepViolations(before, after, 3)).toEqual([]);
  });
  it('flags a stream below its floor and a dangling parent', () => {
    const after = [before[0], before[1], before[4], before[5]];
    const bad = retentionSweepViolations(before, after, 3);
    expect(bad.some((b) => b.includes('below its floor'))).toBe(true);
    expect(bad.some((b) => b.includes('a2'))).toBe(true);
  });
  it('flags a stream that vanished', () => {
    const bad = retentionSweepViolations(before, before.slice(0, 4), 3);
    expect(bad.some((b) => b.includes('stream B'))).toBe(true);
  });
  it('counts distinct streams', () => expect(distinctStreams(before)).toEqual(['A', 'B']));
});

describe('restore records', () => {
  const line = JSON.stringify({
    status: 'restored',
    chunksWanted: 10,
    chunksFetched: 2,
    chunksReused: 8,
    resumed: false,
    seed: 'live',
    seedGuid: GUID_A,
  });
  it('parses only record lines', () => {
    expect(parseRestoreRecord('debug {')).toBeUndefined();
    expect(parseRestoreRecord('{broken "chunksWanted"')).toBeUndefined();
    expect(restoreRecordsOf(`noise\n${line}\n`)).toHaveLength(1);
  });
  it('judges a seeded restore', () => {
    const record = parseRestoreRecord(line)!;
    expect(seededRestoreViolations(record, GUID_A)).toEqual([]);
    expect(
      seededRestoreViolations({ ...record, seed: '', chunksReused: 0, chunksFetched: 10 })
    ).toHaveLength(3);
    expect(seededRestoreViolations(record, GUID_B)).toHaveLength(1);
  });
});

describe('scheduleServiceUnit', () => {
  it('matches the reconcile naming', () =>
    expect(scheduleServiceUnit('nightly')).toBe('rediacc-backup-nightly.service'));
});
