import { describe, expect, it } from 'vitest';
import { detectGuidFiles, resolveGuidFileNames } from '../parsers.js';
import type { RemoteFile } from '../types.js';

const GUID_1 = '550e8400-e29b-41d4-a716-446655440000';
const GUID_2 = '34dc6da3-b844-4b36-bb00-00df42df8f03';

describe('resolveGuidFileNames', () => {
  it('should resolve known GUIDs to display names', () => {
    const files = detectGuidFiles([{ name: GUID_1, size: 2048, isDirectory: false }]);
    const guidMap = { [GUID_1]: 'my-repo:latest' };
    const result = resolveGuidFileNames(files, guidMap);

    expect(result[0].name).toBe('my-repo:latest');
    expect(result[0].originalGuid).toBe(GUID_1);
    expect(result[0].isGuid).toBe(true);
  });

  it('should leave unresolved GUIDs unchanged', () => {
    const files = detectGuidFiles([{ name: GUID_2, size: 1024, isDirectory: false }]);
    const guidMap = { [GUID_1]: 'my-repo:latest' };
    const result = resolveGuidFileNames(files, guidMap);

    expect(result[0].name).toBe(GUID_2);
    expect(result[0].originalGuid).toBe(GUID_2);
  });

  it('should not modify non-GUID files', () => {
    const files: RemoteFile[] = [{ name: 'readme.txt', size: 100, isDirectory: false }];
    const guidMap = { [GUID_1]: 'my-repo:latest' };
    const result = resolveGuidFileNames(files, guidMap);

    expect(result[0].name).toBe('readme.txt');
  });

  it('should return files unchanged when guidMap is empty', () => {
    const files = detectGuidFiles([{ name: GUID_1, size: 2048, isDirectory: false }]);
    const result = resolveGuidFileNames(files, {});

    expect(result[0].name).toBe(GUID_1);
    expect(result[0].isGuid).toBe(true);
  });

  it('should handle mixed resolved and unresolved files', () => {
    const files = detectGuidFiles([
      { name: 'folder', size: 0, isDirectory: true },
      { name: GUID_1, size: 2048, isDirectory: false },
      { name: GUID_2, size: 1024, isDirectory: false },
      { name: 'config.txt', size: 100, isDirectory: false },
    ]);
    const guidMap = { [GUID_1]: 'web-app:latest' };
    const result = resolveGuidFileNames(files, guidMap);

    expect(result[0].name).toBe('folder');
    expect(result[1].name).toBe('web-app:latest');
    expect(result[1].originalGuid).toBe(GUID_1);
    expect(result[2].name).toBe(GUID_2);
    expect(result[2].originalGuid).toBe(GUID_2);
    expect(result[3].name).toBe('config.txt');
  });

  it('should handle empty file list', () => {
    expect(resolveGuidFileNames([], { [GUID_1]: 'repo:latest' })).toEqual([]);
  });

  it('should resolve multiple GUIDs', () => {
    const files = detectGuidFiles([
      { name: GUID_1, size: 2048, isDirectory: false },
      { name: GUID_2, size: 1024, isDirectory: false },
    ]);
    const guidMap = {
      [GUID_1]: 'web-app:latest',
      [GUID_2]: 'database:v2',
    };
    const result = resolveGuidFileNames(files, guidMap);

    expect(result[0].name).toBe('web-app:latest');
    expect(result[1].name).toBe('database:v2');
  });
});
