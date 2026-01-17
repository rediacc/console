import { describe, expect, it } from 'vitest';
import {
  cleanJsonOutput,
  parseFallbackFormats,
  parseJsonFileList,
  parsePlainTextFileList,
  parseRcloneFileList,
} from './parsers';

const mockRepositoryMapper = (guid: string) => ({
  displayName: `repo-${guid}`,
  repositoryName: 'test-repo',
  repositoryTag: 'latest',
  isUnmapped: false,
});

describe('parseJsonFileList', () => {
  it('should parse array of files with basic properties', () => {
    const data = [
      { name: 'file1.txt', size: 1024, isDirectory: false },
      { name: 'folder1', size: 0, isDirectory: true },
    ];

    const result = parseJsonFileList(data, '', mockRepositoryMapper);

    expect(result).toHaveLength(2);
    expect(result[0].name).toBe('file1.txt');
    expect(result[0].size).toBe(1024);
    expect(result[0].isDirectory).toBe(false);
    expect(result[1].name).toBe('folder1');
    expect(result[1].isDirectory).toBe(true);
  });

  it('should handle GUID filenames and map to repositories', () => {
    const guid = '550e8400-e29b-41d4-a716-446655440000';
    const data = [{ name: guid, size: 2048, isDirectory: false }];

    const result = parseJsonFileList(data, '', mockRepositoryMapper);

    expect(result[0].name).toBe(`repo-${guid}`);
    expect(result[0].originalGuid).toBe(guid);
    expect(result[0].repositoryName).toBe('test-repo');
  });

  it('should handle files with Name property (case variation)', () => {
    const data = [{ Name: 'file2.txt', Size: 512, IsDir: false }];

    const result = parseJsonFileList(data, '', mockRepositoryMapper);

    expect(result[0].name).toBe('file2.txt');
    expect(result[0].size).toBe(512);
  });

  it('should construct paths correctly', () => {
    const data = [{ name: 'file.txt', size: 100, isDirectory: false }];

    const result = parseJsonFileList(data, 'folder/subfolder', mockRepositoryMapper);

    expect(result[0].path).toBe('folder/subfolder/file.txt');
  });

  it('should return empty array for non-array input', () => {
    const result = parseJsonFileList({}, '', mockRepositoryMapper);
    expect(result).toEqual([]);
  });
});

describe('parseRcloneFileList', () => {
  it('should parse rclone format with entries wrapper', () => {
    const data = {
      entries: [
        { Name: 'file1.txt', Size: 1024, IsDir: false, ModTime: '2023-01-01T00:00:00Z' },
        { Name: 'folder1', Size: 0, IsDir: true },
      ],
    };

    const result = parseRcloneFileList(data, '', mockRepositoryMapper);

    expect(result).toHaveLength(2);
    expect(result[0].name).toBe('file1.txt');
    expect(result[0].modTime).toBe('2023-01-01T00:00:00Z');
  });

  it('should handle missing entries property', () => {
    const data = { entries: undefined };

    const result = parseRcloneFileList(data, '', mockRepositoryMapper);

    expect(result).toEqual([]);
  });

  it('should include MimeType when present', () => {
    const data = {
      entries: [{ Name: 'image.png', Size: 2048, IsDir: false, MimeType: 'image/png' }],
    };

    const result = parseRcloneFileList(data, '', mockRepositoryMapper);

    expect(result[0].mimeType).toBe('image/png');
  });
});

describe('parsePlainTextFileList', () => {
  it('should parse plain text format with size and name', () => {
    const textData = '1024 file1.txt\n2048 file2.txt';

    const result = parsePlainTextFileList(textData, '');

    expect(result).toHaveLength(2);
    expect(result[0].name).toBe('file1.txt');
    expect(result[0].size).toBe(1024);
    expect(result[1].name).toBe('file2.txt');
    expect(result[1].size).toBe(2048);
  });

  it('should filter out status messages', () => {
    const textData = 'Listing files...\nDEBUG: some debug info\n1024 file1.txt\nError: ignored';

    const result = parsePlainTextFileList(textData, '');

    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('file1.txt');
  });

  it('should handle lines without size prefix', () => {
    const textData = 'file-without-size.txt';

    const result = parsePlainTextFileList(textData, '');

    expect(result[0].name).toBe('file-without-size.txt');
    expect(result[0].size).toBe(0);
  });

  it('should detect directories by trailing slash', () => {
    const textData = '0 folder/';

    const result = parsePlainTextFileList(textData, '');

    expect(result[0].isDirectory).toBe(true);
  });
});

describe('parseFallbackFormats', () => {
  it('should parse malformed rclone JSON with individual objects', () => {
    const textData =
      '{"Name":"file1.txt","Size":1024,"IsDir":false,"Path":"file1.txt"}{"Name":"file2.txt","Size":2048,"IsDir":false,"Path":"file2.txt"}';

    const result = parseFallbackFormats(textData, '');

    expect(result).toHaveLength(2);
    expect(result[0].name).toBe('file1.txt');
    expect(result[1].name).toBe('file2.txt');
  });

  it('should return empty array if format not recognized', () => {
    const textData = 'some random text';

    const result = parseFallbackFormats(textData, '');

    expect(result).toEqual([]);
  });

  it('should skip invalid JSON objects', () => {
    const textData =
      '{"Name":"valid.txt","Size":100,"IsDir":false,"Path":"valid.txt"}{"Invalid JSON}';

    const result = parseFallbackFormats(textData, '');

    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('valid.txt');
  });
});

describe('cleanJsonOutput', () => {
  it('should extract JSON array from debug output', () => {
    const input = 'DEBUG: Loading...\nDEBUG: Processing...\n[{"name":"file.txt"}]';

    const result = cleanJsonOutput(input);

    expect(result).toBe('[{"name":"file.txt"}]');
  });

  it('should clean escaped backslashes and newlines', () => {
    const input = 'prefix text [{"name":"file\\ntest"}]';

    const result = cleanJsonOutput(input);

    expect(result).toBe('[{"name":"file\ntest"}]');
  });

  it('should return original if no JSON array found', () => {
    const input = 'plain text without json';

    const result = cleanJsonOutput(input);

    expect(result).toBe(input);
  });

  it('should handle multiple brackets correctly', () => {
    const input = 'Text [ignore] this [{"name":"file.txt"}]';

    const result = cleanJsonOutput(input);

    expect(result).toContain('[{"name":"file.txt"}]');
  });
});
