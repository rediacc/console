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

  describe('user CRUD operations', () => {
    let testUserEmail: string;

    it('should create a new user', async () => {
      testUserEmail = `test-crud-${Date.now()}@rediacc-test.local`;
      const result = await runCli(['user', 'create', testUserEmail]);

      if (!result.success) {
        console.error('User create failed:', result.stderr || result.stdout);
      }
      expect(result.success, `Failed: ${result.stderr || result.stdout}`).toBe(true);
      expect(result.stdout).toContain('User created');
    });

    it('should assign permission group to user', async () => {
      // Get a permission group name
      const groups = await runCli(['permission', 'group', 'list']);
      if (!groups.success) {
        console.error('Permission group list failed:', groups.stderr || groups.stdout);
      }
      expect(groups.success, `Failed: ${groups.stderr || groups.stdout}`).toBe(true);

      const groupList = groups.json as { permissionGroupName: string }[];
      expect(groupList.length).toBeGreaterThan(0);

      const groupName = groupList[0].permissionGroupName;
      const result = await runCli(['user', 'permission', 'assign', testUserEmail, groupName]);

      if (!result.success) {
        console.error('Permission assign failed:', result.stderr || result.stdout);
      }
      expect(result.success, `Failed: ${result.stderr || result.stdout}`).toBe(true);
      expect(result.stdout).toContain('Permission assigned');
    });
  });

  describe('user update-email', () => {
    it('should update user email', async () => {
      const timestamp = Date.now();
      const oldEmail = `test-email-old-${timestamp}@rediacc-test.local`;
      const newEmail = `test-email-new-${timestamp}@rediacc-test.local`;

      // Create user first
      const createResult = await runCli(['user', 'create', oldEmail]);
      if (!createResult.success) {
        console.error('User create failed:', createResult.stderr || createResult.stdout);
      }
      expect(createResult.success, `Failed: ${createResult.stderr || createResult.stdout}`).toBe(
        true
      );

      // Update email
      const result = await runCli(['user', 'update-email', oldEmail, newEmail]);
      if (!result.success) {
        console.error('Email update failed:', result.stderr || result.stdout);
      }
      expect(result.success, `Failed: ${result.stderr || result.stdout}`).toBe(true);
      expect(result.stdout).toContain('Email updated');
    });
  });

  describe('user update-password', () => {
    it('should update password with --password flag', async () => {
      const newPassword = `TestPass${Date.now()}!`;
      const result = await runCli([
        'user',
        'update-password',
        '--password',
        newPassword,
        '--confirm',
        newPassword,
      ]);

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('Password updated');
    });

    it('should reject mismatched passwords', async () => {
      const result = await runCli([
        'user',
        'update-password',
        '--password',
        'Password123!',
        '--confirm',
        'DifferentPassword456!',
      ]);

      expect(result.success).toBe(false);
      expect(result.stderr).toContain('Passwords do not match');
    });
  });
});
