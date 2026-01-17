import { describe, expect, it } from 'vitest';
import { parseLogLevel, parseLogLine, parseLogOutput } from '../logParser';

describe('logParser', () => {
  describe('parseLogLevel', () => {
    it('should parse standard log levels', () => {
      expect(parseLogLevel('info')).toBe('info');
      expect(parseLogLevel('INFO')).toBe('info');
      expect(parseLogLevel('warning')).toBe('warning');
      expect(parseLogLevel('warn')).toBe('warning');
      expect(parseLogLevel('error')).toBe('error');
      expect(parseLogLevel('debug')).toBe('debug');
    });

    it('should map fatal/panic to error', () => {
      expect(parseLogLevel('fatal')).toBe('error');
      expect(parseLogLevel('panic')).toBe('error');
    });

    it('should return info for unrecognized levels', () => {
      expect(parseLogLevel('custom')).toBe('info');
      expect(parseLogLevel('unknown')).toBe('info');
    });
  });

  describe('parseLogLine', () => {
    it('should parse simple message with prefix', () => {
      const result = parseLogLine('[repository_create] Starting...', 0);
      expect(result.prefix).toBe('repository_create');
      expect(result.message).toBe('Starting...');
      expect(result.isStructured).toBe(false);
      expect(result.level).toBe('info');
    });

    it('should parse structured log with all fields', () => {
      const line =
        '[repository_create] time="2026-01-02T13:34:39Z" level=info msg="Creating repository" name=test size=1G';
      const result = parseLogLine(line, 0);

      expect(result.prefix).toBe('repository_create');
      expect(result.time).toBe('2026-01-02T13:34:39Z');
      expect(result.level).toBe('info');
      expect(result.message).toBe('Creating repository');
      expect(result.extras).toEqual({ name: 'test', size: '1G' });
      expect(result.isStructured).toBe(true);
    });

    it('should parse warning level', () => {
      const line =
        '[test] time="2026-01-02T13:34:39Z" level=warning msg="Could not detect network"';
      const result = parseLogLine(line, 0);

      expect(result.level).toBe('warning');
      expect(result.isStructured).toBe(true);
    });

    it('should handle completion messages', () => {
      const line = '[repository_create] Complete: repository_create completed successfully';
      const result = parseLogLine(line, 0);

      expect(result.prefix).toBe('repository_create');
      expect(result.message).toBe('Complete: repository_create completed successfully');
      expect(result.isStructured).toBe(false);
    });

    it('should handle empty lines', () => {
      const result = parseLogLine('', 0);
      expect(result.message).toBe('');
      expect(result.isStructured).toBe(false);
    });

    it('should handle lines without prefix', () => {
      const result = parseLogLine('Some plain message', 0);
      expect(result.prefix).toBeUndefined();
      expect(result.message).toBe('Some plain message');
      expect(result.isStructured).toBe(false);
    });

    it('should handle quoted values with spaces in extras', () => {
      const line =
        '[test] time="2026-01-02T13:34:39Z" level=info msg="Test" path="/home/user/my folder"';
      const result = parseLogLine(line, 0);

      expect(result.extras?.path).toBe('/home/user/my folder');
    });
  });

  describe('parseLogOutput', () => {
    it('should parse multiple lines', () => {
      const content = `[test] Starting...
[test] time="2026-01-02T13:34:39Z" level=info msg="Processing"
[test] Complete`;

      const results = parseLogOutput(content);

      expect(results).toHaveLength(3);
      expect(results[0].isStructured).toBe(false);
      expect(results[0].message).toBe('Starting...');
      expect(results[1].isStructured).toBe(true);
      expect(results[1].message).toBe('Processing');
      expect(results[2].isStructured).toBe(false);
      expect(results[2].message).toBe('Complete');
    });

    it('should handle escaped newlines', () => {
      const content = '[test] time="2026-01-02T13:34:39Z" level=info msg="Line1"\\n[test] Line2';
      const results = parseLogOutput(content);

      expect(results.length).toBeGreaterThanOrEqual(1);
    });

    it('should filter empty lines', () => {
      const content = `[test] Starting...

[test] Complete`;

      const results = parseLogOutput(content);

      expect(results).toHaveLength(2);
    });

    it('should return empty array for empty content', () => {
      expect(parseLogOutput('')).toEqual([]);
    });

    it('should parse real-world repository_create output', () => {
      const content = `[repository_create] Starting...
[repository_create] time="2026-01-02T13:34:39Z" level=warning msg="Could not detect network ID."
[repository_create] time="2026-01-02T13:34:39Z" level=info msg="Creating repository '4deaf44f' with size 1G"
[repository_create] time="2026-01-02T13:34:39Z" level=info msg="Repository created successfully" encrypted=false name=4deaf44f size=1G
[repository_create] Complete: repository_create completed successfully`;

      const results = parseLogOutput(content);

      expect(results).toHaveLength(5);

      // First line - simple message
      expect(results[0].message).toBe('Starting...');
      expect(results[0].isStructured).toBe(false);

      // Second line - warning
      expect(results[1].level).toBe('warning');
      expect(results[1].message).toBe('Could not detect network ID.');

      // Third line - info with quoted message
      expect(results[2].level).toBe('info');
      expect(results[2].message).toBe("Creating repository '4deaf44f' with size 1G");

      // Fourth line - info with extras
      expect(results[3].level).toBe('info');
      expect(results[3].extras?.encrypted).toBe('false');
      expect(results[3].extras?.name).toBe('4deaf44f');

      // Last line - completion
      expect(results[4].message).toBe('Complete: repository_create completed successfully');
    });
  });
});
