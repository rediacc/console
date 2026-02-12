import { describe, expect, it } from 'vitest';
import { detectGuidFiles, FileListParserFactory } from '../parsers.js';
import type { RemoteFile } from '../types.js';

const GUID = '550e8400-e29b-41d4-a716-446655440000';
const GUID_UPPER = '550E8400-E29B-41D4-A716-446655440000';

describe('detectGuidFiles', () => {
  it('should mark GUID-named files with isGuid and originalGuid', () => {
    const files: RemoteFile[] = [{ name: GUID, size: 2048, isDirectory: false }];
    const result = detectGuidFiles(files);
    expect(result).toHaveLength(1);
    expect(result[0].isGuid).toBe(true);
    expect(result[0].originalGuid).toBe(GUID);
    expect(result[0].name).toBe(GUID); // name is NOT overwritten
  });

  it('should handle uppercase GUIDs (case-insensitive)', () => {
    const files: RemoteFile[] = [{ name: GUID_UPPER, size: 100, isDirectory: false }];
    const result = detectGuidFiles(files);
    expect(result[0].isGuid).toBe(true);
    expect(result[0].originalGuid).toBe(GUID_UPPER);
  });

  it('should not mark regular filenames', () => {
    const files: RemoteFile[] = [
      { name: 'backup.tar.gz', size: 1024, isDirectory: false },
      { name: 'report.pdf', size: 512, isDirectory: false },
    ];
    const result = detectGuidFiles(files);
    expect(result[0].isGuid).toBeUndefined();
    expect(result[0].originalGuid).toBeUndefined();
    expect(result[1].isGuid).toBeUndefined();
  });

  it('should mark GUID-named directories', () => {
    const files: RemoteFile[] = [{ name: GUID, size: 0, isDirectory: true }];
    const result = detectGuidFiles(files);
    expect(result[0].isGuid).toBe(true);
    expect(result[0].isDirectory).toBe(true);
  });

  it('should handle empty array', () => {
    expect(detectGuidFiles([])).toEqual([]);
  });

  it('should handle mixed GUID and non-GUID files', () => {
    const files: RemoteFile[] = [
      { name: 'folder', size: 0, isDirectory: true },
      { name: GUID, size: 2048, isDirectory: false },
      { name: 'readme.txt', size: 100, isDirectory: false },
    ];
    const result = detectGuidFiles(files);
    expect(result[0].isGuid).toBeUndefined();
    expect(result[1].isGuid).toBe(true);
    expect(result[2].isGuid).toBeUndefined();
  });

  it('should not mark partial GUIDs', () => {
    const files: RemoteFile[] = [
      { name: '550e8400-e29b-41d4', size: 100, isDirectory: false },
      { name: 'not-a-guid-at-all', size: 100, isDirectory: false },
    ];
    const result = detectGuidFiles(files);
    expect(result[0].isGuid).toBeUndefined();
    expect(result[1].isGuid).toBeUndefined();
  });

  it('should not mark GUID with extension', () => {
    const files: RemoteFile[] = [{ name: `${GUID}.tar.gz`, size: 100, isDirectory: false }];
    const result = detectGuidFiles(files);
    // Matches web behavior: only exact GUID filenames match
    expect(result[0].isGuid).toBeUndefined();
  });
});

describe('FileListParserFactory with detectGuids option', () => {
  it('should annotate GUID files when detectGuids is true', () => {
    const data = JSON.stringify([
      { name: GUID, size: 2048, isDirectory: false },
      { name: 'report.txt', size: 100, isDirectory: false },
    ]);
    const parser = new FileListParserFactory('', { detectGuids: true });
    const result = parser.parse(data);

    expect(result).toHaveLength(2);
    expect(result[0].isGuid).toBe(true);
    expect(result[0].originalGuid).toBe(GUID);
    expect(result[1].isGuid).toBeUndefined();
  });

  it('should NOT annotate when detectGuids is omitted', () => {
    const data = JSON.stringify([{ name: GUID, size: 2048, isDirectory: false }]);
    const parser = new FileListParserFactory('');
    const result = parser.parse(data);

    expect(result[0].isGuid).toBeUndefined();
    expect(result[0].originalGuid).toBeUndefined();
  });

  it('should NOT annotate when detectGuids is false', () => {
    const data = JSON.stringify([{ name: GUID, size: 2048, isDirectory: false }]);
    const parser = new FileListParserFactory('', { detectGuids: false });
    const result = parser.parse(data);

    expect(result[0].isGuid).toBeUndefined();
  });
});
