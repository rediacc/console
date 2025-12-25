import { describe, it, expect, beforeAll } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('user commands', () => {
  beforeAll(async () => {
    // Ensure we're authenticated
    await runCli(['team', 'list']);
  });

  describe('user list', () => {
    it('should list all users', async () => {
      const result = await runCli(['user', 'list']);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const users = result.json as unknown[];
      if (users.length > 0) {
        const user = users[0] as Record<string, unknown>;
        expect(user).toHaveProperty('userEmail');
      }
    });
  });

  describe('user vault', () => {
    it('should get current user vault', async () => {
      const result = await runCli(['user', 'vault', 'get']);

      expect(result.success).toBe(true);
      expect(result.json).not.toBeNull();
    });
  });

  describe('user update-language', () => {
    it('should update language preference', async () => {
      const result = await runCli(['user', 'update-language', 'en']);

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('Language updated');
    });
  });

  describe('user deactivate and reactivate', () => {
    let testUserEmail: string;

    beforeAll(async () => {
      // Create a fresh user for testing deactivate/reactivate
      const timestamp = Date.now();
      testUserEmail = `test-deact-${timestamp}@rediacc-test.local`;

      const createResult = await runCli(['user', 'create', testUserEmail]);
      expect(createResult.success).toBe(true);
    });

    it('should deactivate a user', async () => {
      const result = await runCli(['user', 'deactivate', testUserEmail, '--force']);

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('User deactivated');
    });

    it('should reactivate a user', async () => {
      const result = await runCli(['user', 'reactivate', testUserEmail]);

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('User reactivated');
    });
  });

  // Note: user CRUD operations are sensitive and skipped
  describe.skip('user CRUD operations', () => {
    it('should invite a new user', async () => {
      // User invitations send real emails
    });

    it('should update user permissions', async () => {
      // Permissions changes are sensitive
    });
  });

  describe.skip('user update-email', () => {
    it('should update user email', async () => {
      // Email changes are sensitive and require verification
    });
  });

  describe.skip('user update-password', () => {
    it('should update password', async () => {
      // Requires interactive password input
    });
  });
});
