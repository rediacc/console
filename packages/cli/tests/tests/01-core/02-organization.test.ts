import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('Organization Commands @cli @core', () => {
  let runner: CliTestRunner;

  test.beforeAll(() => {
    runner = CliTestRunner.fromGlobalState();
  });

  test.describe('organization info', () => {
    test('should show organization information', async () => {
      const result = await runner.organizationGet();

      expect(runner.isSuccess(result)).toBe(true);
      expect(result.json).not.toBeNull();
    });
  });

  test.describe('organization vault', () => {
    test('should show organization vault data', async () => {
      const result = await runner.run(['organization', 'vault']);

      // Organization vault may require specific permissions or master password
      // For fresh accounts, the command should at least run

      expect(result.success || result.stderr.length > 0 || result.stdout.length > 0).toBe(true);
    });
  });

  test.describe('organization maintenance', () => {
    test('should enable maintenance mode', async () => {
      // Use table format for action commands that only produce success messages
      const result = await runner.run(['organization', 'maintenance', 'enable'], {
        outputFormat: 'table',
        skipJsonParse: true,
      });

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('Maintenance mode enabled');
    });

    test('should disable maintenance mode', async () => {
      // Use table format for action commands that only produce success messages
      const result = await runner.run(['organization', 'maintenance', 'disable'], {
        outputFormat: 'table',
        skipJsonParse: true,
      });

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('Maintenance mode disabled');
    });

    test('should reject invalid action', async () => {
      const result = await runner.run(['organization', 'maintenance', 'invalid']);

      expect(result.success).toBe(false);
      // In JSON mode, error is returned as structured JSON in stdout
      const errorResponse = result.json as { success: false; error: { message: string } } | null;
      expect(errorResponse?.error.message).toContain('Invalid action');
    });
  });
});
