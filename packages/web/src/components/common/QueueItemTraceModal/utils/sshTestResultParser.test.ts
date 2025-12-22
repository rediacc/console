import { describe, it, expect } from 'vitest';
import { parseSSHTestResults } from './sshTestResultParser';

describe('sshTestResultParser', () => {
  describe('parseSSHTestResults', () => {
    it('should parse valid SSH test result from string content', () => {
      const vaultContent = JSON.stringify({
        result: JSON.stringify({
          status: 'success',
          ip: '192.168.1.100',
          user: 'root',
          auth_method: 'key',
          ssh_key_configured: true,
          kernel_compatibility: {
            kernel_version: '5.15.0',
            btrfs_available: true,
            sudo_available: 'available',
            compatibility_status: 'compatible',
          },
        }),
      });

      const result = parseSSHTestResults(vaultContent);
      expect(result.isSSHTest).toBe(true);
      expect(result.result?.status).toBe('success');
      expect(result.result?.ip).toBe('192.168.1.100');
      expect(result.result?.kernel_compatibility.compatibility_status).toBe('compatible');
    });

    it('should parse valid SSH test result from object content', () => {
      const vaultContent = {
        result: JSON.stringify({
          status: 'success',
          ip: '10.0.0.5',
          user: 'admin',
          auth_method: 'password',
          ssh_key_configured: false,
          kernel_compatibility: {
            kernel_version: '6.1.0',
            btrfs_available: false,
            sudo_available: 'password_required',
            compatibility_status: 'warning',
          },
        }),
      };

      const result = parseSSHTestResults(vaultContent);
      expect(result.isSSHTest).toBe(true);
      expect(result.result?.status).toBe('success');
      expect(result.result?.ssh_key_configured).toBe(false);
      expect(result.result?.kernel_compatibility.compatibility_status).toBe('warning');
    });

    it('should return isSSHTest false for content without result field', () => {
      const vaultContent = {
        data: 'some other data',
        status: 'success',
      };

      const result = parseSSHTestResults(vaultContent);
      expect(result.isSSHTest).toBe(false);
      expect(result.result).toBeUndefined();
    });

    it('should return isSSHTest false for content with non-string result', () => {
      const vaultContent = {
        result: { some: 'object' },
      };

      const result = parseSSHTestResults(vaultContent);
      expect(result.isSSHTest).toBe(false);
      expect(result.result).toBeUndefined();
    });

    it('should return isSSHTest false for result without kernel_compatibility', () => {
      const vaultContent = {
        result: JSON.stringify({
          status: 'success',
          ip: '192.168.1.100',
          user: 'root',
        }),
      };

      const result = parseSSHTestResults(vaultContent);
      expect(result.isSSHTest).toBe(false);
      expect(result.result).toBeUndefined();
    });

    it('should handle invalid JSON in vault content', () => {
      const vaultContent = 'invalid json {{{';

      const result = parseSSHTestResults(vaultContent);
      expect(result.isSSHTest).toBe(false);
      expect(result.result).toBeUndefined();
    });

    it('should handle invalid JSON in result field', () => {
      const vaultContent = {
        result: 'invalid json {{{',
      };

      const result = parseSSHTestResults(vaultContent);
      expect(result.isSSHTest).toBe(false);
      expect(result.result).toBeUndefined();
    });

    it('should handle null or undefined content', () => {
      expect(parseSSHTestResults(null).isSSHTest).toBe(false);
      expect(parseSSHTestResults(undefined).isSSHTest).toBe(false);
    });

    it('should parse SSH test result with full compatibility data', () => {
      const vaultContent = {
        result: JSON.stringify({
          status: 'success',
          machine: 'prod-server-01',
          ip: '192.168.1.100',
          user: 'root',
          auth_method: 'key',
          ssh_key_configured: true,
          kernel_compatibility: {
            kernel_version: '5.15.0-100-generic',
            btrfs_available: true,
            sudo_available: 'available',
            compatibility_status: 'warning',
            compatibility_issues: ['Issue 1', 'Issue 2'],
            recommendations: ['Recommendation 1', 'Recommendation 2'],
            os_info: {
              pretty_name: 'Ubuntu 22.04 LTS',
              id: 'ubuntu',
              version_id: '22.04',
            },
          },
        }),
      };

      const result = parseSSHTestResults(vaultContent);
      expect(result.isSSHTest).toBe(true);
      expect(result.result?.machine).toBe('prod-server-01');
      expect(result.result?.kernel_compatibility.compatibility_issues).toHaveLength(2);
      expect(result.result?.kernel_compatibility.recommendations).toHaveLength(2);
      expect(result.result?.kernel_compatibility.os_info?.pretty_name).toBe('Ubuntu 22.04 LTS');
    });
  });
});
