import { describe, expect, it } from 'vitest';
import { parseVaultStatus } from '@rediacc/shared/services/machine';

describe('parseVaultStatus', () => {
  describe('encrypted data detection', () => {
    it('should detect base64 encrypted data', () => {
      const encrypted = 'YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY3ODkwMTIzNDU2Nzg5MA==';
      const result = parseVaultStatus(encrypted);
      expect(result.error).toBe('encrypted');
    });

    it('should detect long base64 strings as encrypted', () => {
      // Real-world encrypted data pattern (AES-GCM output)
      const encrypted =
        'u/nuf2Fr6ycs6sFOwuihZffcIwJCHDNyIk4FNnfDrh6hrNKHWURnRUjH8Lzro0bnLOG8SSbh15Z58pAHDEI6Ula5z1';
      const result = parseVaultStatus(encrypted);
      expect(result.error).toBe('encrypted');
    });

    it('should not treat valid JSON as encrypted', () => {
      const json = '{"status": "completed", "result": "{}"}';
      const result = parseVaultStatus(json);
      expect(result.error).not.toBe('encrypted');
    });

    it('should not treat short strings as encrypted', () => {
      const short = 'abc123';
      const result = parseVaultStatus(short);
      expect(result.error).not.toBe('encrypted');
    });

    it('should handle null', () => {
      expect(parseVaultStatus(null).status).toBe('unknown');
      expect(parseVaultStatus(null).repositories).toEqual([]);
    });

    it('should handle undefined', () => {
      expect(parseVaultStatus(undefined).status).toBe('unknown');
      expect(parseVaultStatus(undefined).repositories).toEqual([]);
    });

    it('should handle empty string', () => {
      expect(parseVaultStatus('').status).toBe('unknown');
      expect(parseVaultStatus('').repositories).toEqual([]);
    });

    it('should handle whitespace-padded base64', () => {
      const padded = '  YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY3ODkw  ';
      const result = parseVaultStatus(padded);
      expect(result.error).toBe('encrypted');
    });

    it('should not treat JSON starting with { as encrypted', () => {
      const json = '{"key": "value"}';
      const result = parseVaultStatus(json);
      expect(result.error).not.toBe('encrypted');
    });

    it('should not treat nested JSON with base64 values as encrypted', () => {
      const json = '{"data": "YWJjZGVm", "status": "ok"}';
      const result = parseVaultStatus(json);
      expect(result.error).not.toBe('encrypted');
    });
  });

  describe('valid vault status parsing', () => {
    it('should parse raw format with repositories', () => {
      const vaultStatus = JSON.stringify({
        repositories: [{ name: 'test-repo', mounted: true }],
        system: { hostname: 'test-machine' },
      });
      const result = parseVaultStatus(vaultStatus);
      expect(result.status).toBe('completed');
      expect(result.repositories).toHaveLength(1);
      expect(result.repositories[0].name).toBe('test-repo');
    });

    it('should parse raw format with empty repositories', () => {
      const vaultStatus = JSON.stringify({
        repositories: [],
        system: { hostname: 'test-machine' },
      });
      const result = parseVaultStatus(vaultStatus);
      expect(result.status).toBe('completed');
      expect(result.repositories).toEqual([]);
    });

    it('should parse raw format with system info only', () => {
      const vaultStatus = JSON.stringify({
        system: { hostname: 'test-machine', uptime: '10 days' },
      });
      const result = parseVaultStatus(vaultStatus);
      expect(result.status).toBe('completed');
      expect(result.repositories).toEqual([]);
    });

    it('should parse full ListResult format', () => {
      const vaultStatus = JSON.stringify({
        system: {
          hostname: 'test-machine',
          memory: { total: '16G', used: '8G' },
          disk: { total: '100G', used: '50G' },
        },
        repositories: [
          { name: 'repo-1', mounted: true, docker_running: true },
          { name: 'repo-2', mounted: false, docker_running: false },
        ],
        containers: { containers: [], total_count: 0 },
        services: { services: [], total_count: 0 },
      });
      const result = parseVaultStatus(vaultStatus);
      expect(result.status).toBe('completed');
      expect(result.repositories).toHaveLength(2);
      expect(result.repositories[0].mounted).toBe(true);
      expect(result.repositories[1].mounted).toBe(false);
    });
  });

  describe('error handling', () => {
    it('should return error for jq: prefix', () => {
      const result = parseVaultStatus('jq: error: invalid json');
      expect(result.error).toBeDefined();
      expect(result.status).toBe('unknown');
    });

    it('should return error for error: prefix', () => {
      const result = parseVaultStatus('error: something went wrong');
      expect(result.error).toBeDefined();
      expect(result.status).toBe('unknown');
    });

    it('should handle malformed JSON gracefully', () => {
      const result = parseVaultStatus('{ invalid json }');
      expect(result.status).toBe('unknown');
    });
  });
});
