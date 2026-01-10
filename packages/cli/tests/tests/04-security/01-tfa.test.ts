import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { ErrorPatterns, expectError } from '../../src/utils/errors';
import {
  disableTFA,
  extractSecret,
  generateFreshTOTPCode,
  getTFAStatus,
} from '../../src/utils/tfa';

test.describe('TFA (Two-Factor Authentication) @cli @security', () => {
  let runner: CliTestRunner;
  let tfaSecret: string | null = null;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Ensure we're authenticated
    await runner.teamList();

    // Check if TFA is already enabled and disable it for clean state
    const status = await getTFAStatus(runner);
    if (status.enabled) {
      console.warn('TFA was already enabled - cannot clean state without existing secret');
    }
  });

  test.afterAll(async () => {
    // Cleanup: ensure TFA is disabled after tests
    if (tfaSecret) {
      try {
        await disableTFA(runner, tfaSecret);
      } catch {
        console.warn('Failed to cleanup TFA state after tests');
      }
    }
  });

  test.describe('auth tfa status', () => {
    test('should show TFA status', async () => {
      const result = await runner.run(['auth', 'tfa', 'status']);

      expect(runner.isSuccess(result)).toBe(true);
      // Should contain either "enabled" or "not enabled"
      expect(result.stdout).toMatch(/enabled/i);
    });
  });

  test.describe('auth tfa enable', () => {
    test('should enable TFA and return a secret', async () => {
      const result = await runner.run(['auth', 'tfa', 'enable']);

      if (!result.success) {
        const errorMsg = runner.getErrorMessage(result);
        // If TFA is already enabled, that's a known state
        if (errorMsg.includes('already enabled')) {
          console.warn('Skipping test - TFA is already enabled on this account');
          return;
        }
        console.error('TFA enable failed:', errorMsg);
      }

      expect(result.success, `Failed: ${runner.getErrorMessage(result)}`).toBe(true);

      // Extract and validate secret
      tfaSecret = extractSecret(result);
      expect(tfaSecret, 'Expected a TFA secret to be returned').not.toBeNull();
      expect(tfaSecret).toMatch(/^[A-Z2-7]{32}$/);
    });

    test('should fail when TFA is already enabled', async () => {
      // Skip if we don't have a secret (previous test didn't enable TFA)
      if (!tfaSecret) {
        console.warn('Skipping test - no TFA secret available');
        return;
      }

      const result = await runner.run(['auth', 'tfa', 'enable']);

      expectError(runner, result, { messageContains: ErrorPatterns.TFA_ALREADY_ENABLED });
    });
  });

  test.describe('auth tfa status (after enabling)', () => {
    test('should show TFA is enabled', async () => {
      if (!tfaSecret) {
        console.warn('Skipping test - no TFA secret available');
        return;
      }

      const result = await runner.run(['auth', 'tfa', 'status']);

      expect(runner.isSuccess(result)).toBe(true);
      expect(result.stdout).toMatch(/enabled/i);
      expect(result.stdout).not.toMatch(/not enabled/i);
    });
  });

  test.describe('auth tfa disable', () => {
    test('should fail with invalid code', async () => {
      if (!tfaSecret) {
        console.warn('Skipping test - no TFA secret available');
        return;
      }

      const result = await runner.run(['auth', 'tfa', 'disable', '--code', '000000', '--yes']);

      expectError(runner, result, { messageContains: ErrorPatterns.TFA_INVALID_CODE });
    });

    test('should fail with wrong format code', async () => {
      if (!tfaSecret) {
        console.warn('Skipping test - no TFA secret available');
        return;
      }

      const result = await runner.run(['auth', 'tfa', 'disable', '--code', 'abc123', '--yes']);

      // Should fail - either validation error or invalid code
      expect(result.success).toBe(false);
    });

    test('should succeed with valid code', async () => {
      if (!tfaSecret) {
        console.warn('Skipping test - no TFA secret available');
        return;
      }

      // Use fresh TOTP code to avoid timing issues (codes expire every 30s)
      const code = await generateFreshTOTPCode(tfaSecret);
      const result = await runner.run(['auth', 'tfa', 'disable', '--code', code, '--yes']);

      if (!result.success) {
        console.error('TFA disable failed:', runner.getErrorMessage(result));
      }

      expect(result.success, `Failed: ${runner.getErrorMessage(result)}`).toBe(true);
      // Note: In JSON output mode, spinner success messages are not written to stdout
      // So we just verify the command succeeded (exit code 0)

      tfaSecret = null; // Mark as disabled
    });
  });

  test.describe('auth tfa disable (when not enabled)', () => {
    test('should fail when TFA is not enabled', async () => {
      // At this point TFA should be disabled from the previous test
      const result = await runner.run(['auth', 'tfa', 'disable', '--code', '123456', '--yes']);

      expectError(runner, result, { messageContains: ErrorPatterns.TFA_NOT_ENABLED });
    });
  });

  test.describe('auth tfa status (after disabling)', () => {
    test('should show TFA is not enabled', async () => {
      const result = await runner.run(['auth', 'tfa', 'status']);

      expect(runner.isSuccess(result)).toBe(true);
      expect(result.stdout).toMatch(/not enabled/i);
    });
  });
});
