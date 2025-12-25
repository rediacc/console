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

  // Note: user CRUD operations are sensitive and skipped
  describe.skip('user CRUD operations', () => {
    it('should invite a new user', async () => {
      // User invitations send real emails
    });

    it('should update user permissions', async () => {
      // Permissions changes are sensitive
    });
  });
});
