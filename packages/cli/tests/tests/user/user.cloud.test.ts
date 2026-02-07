import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('User Commands @cli @operations', () => {
  let runner: CliTestRunner;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Ensure we're authenticated
    await runner.teamList();
  });

  test.describe('user list', () => {
    test('should list all users', async () => {
      const result = await runner.userList();

      expect(runner.isSuccess(result)).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const users = runner.expectSuccessArray<{ userEmail: string }>(result);
      if (users.length > 0) {
        expect(users[0]).toHaveProperty('userEmail');
      }
    });
  });

  test.describe('user vault', () => {
    test('should get current user vault', async () => {
      const result = await runner.run(['user', 'vault', 'get']);

      expect(runner.isSuccess(result)).toBe(true);
      expect(result.json).not.toBeNull();
    });
  });

  test.describe('user update-language', () => {
    test('should update language preference', async () => {
      // Use table format for action commands that only produce success messages
      const result = await runner.run(['user', 'update-language', 'en'], {
        outputFormat: 'table',
        skipJsonParse: true,
      });

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('Language updated');
    });
  });

  test.describe('user deactivate and reactivate', () => {
    let testUserEmail: string;

    test.beforeAll(async () => {
      // Create a fresh user for testing deactivate/reactivate
      const timestamp = Date.now();
      testUserEmail = `test-deact-${timestamp}@rediacc-test.local`;

      // Use table format for action commands
      const createResult = await runner.run(
        ['user', 'create', testUserEmail, '-p', 'TestPassword123!'],
        { outputFormat: 'table', skipJsonParse: true }
      );
      expect(createResult.exitCode).toBe(0);
    });

    test('should deactivate a user', async () => {
      // Use table format for action commands
      const result = await runner.run(['user', 'deactivate', testUserEmail, '--force'], {
        outputFormat: 'table',
        skipJsonParse: true,
      });

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('deactivated');
    });

    test('should reactivate a user', async () => {
      // Use table format for action commands
      const result = await runner.run(['user', 'reactivate', testUserEmail], {
        outputFormat: 'table',
        skipJsonParse: true,
      });

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('reactivated');
    });
  });

  test.describe('user CRUD operations', () => {
    let testUserEmail: string;

    test('should create a new user', async () => {
      testUserEmail = `test-crud-${Date.now()}@rediacc-test.local`;
      // Use table format for action commands
      const result = await runner.run(['user', 'create', testUserEmail, '-p', 'TestPassword123!'], {
        outputFormat: 'table',
        skipJsonParse: true,
      });

      if (result.exitCode !== 0) {
        console.error('User create failed:', result.stderr || result.stdout);
      }
      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('created');
    });

    test('should assign permission group to user', async () => {
      // Get a permission group name
      const groups = await runner.run(['permission', 'group', 'list']);
      if (!groups.success) {
        console.error('Permission group list failed:', runner.getErrorMessage(groups));
      }
      expect(groups.success, `Failed: ${runner.getErrorMessage(groups)}`).toBe(true);

      const groupList = runner.expectSuccessArray<{ permissionGroupName: string }>(groups);
      expect(groupList.length).toBeGreaterThan(0);

      const groupName = groupList[0].permissionGroupName;
      // Use table format for action commands
      const result = await runner.run(['user', 'permission', 'assign', testUserEmail, groupName], {
        outputFormat: 'table',
        skipJsonParse: true,
      });

      if (result.exitCode !== 0) {
        console.error('Permission assign failed:', result.stderr || result.stdout);
      }
      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('assigned');
    });
  });

  test.describe('user update-email', () => {
    test('should update user email', async () => {
      const timestamp = Date.now();
      const oldEmail = `test-email-old-${timestamp}@rediacc-test.local`;
      const newEmail = `test-email-new-${timestamp}@rediacc-test.local`;

      // Create user first using table format
      const createResult = await runner.run(
        ['user', 'create', oldEmail, '-p', 'TestPassword123!'],
        { outputFormat: 'table', skipJsonParse: true }
      );
      if (createResult.exitCode !== 0) {
        console.error('User create failed:', createResult.stderr || createResult.stdout);
      }
      expect(createResult.exitCode).toBe(0);

      // Update email using table format
      const result = await runner.run(['user', 'update-email', oldEmail, newEmail], {
        outputFormat: 'table',
        skipJsonParse: true,
      });
      if (result.exitCode !== 0) {
        console.error('Email update failed:', result.stderr || result.stdout);
      }
      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('updated');
    });
  });

  test.describe('user update-password', () => {
    test('should update password with --password flag', async () => {
      const newPassword = `TestPass${Date.now()}!`;
      // Use table format for action commands
      const result = await runner.run(
        ['user', 'update-password', '--password', newPassword, '--confirm', newPassword],
        { outputFormat: 'table', skipJsonParse: true }
      );

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('Password updated');
    });

    test('should reject mismatched passwords', async () => {
      const result = await runner.run([
        'user',
        'update-password',
        '--password',
        'Password123!',
        '--confirm',
        'DifferentPassword456!',
      ]);

      expect(result.success).toBe(false);
      // In JSON mode, error is returned as structured JSON in stdout
      const errorResponse = result.json as { success: false; error: { message: string } } | null;
      expect(errorResponse?.error.message).toContain('Passwords do not match');
    });
  });
});
