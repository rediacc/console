import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { runCli, getErrorMessage } from './helpers/cli.js';
import { expectError, ErrorPatterns } from './helpers/errors.js';
import { generateTOTPCode, extractSecret, disableTFA, getTFAStatus } from './helpers/tfa.js';

describe('TFA (Two-Factor Authentication)', () => {
  let tfaSecret: string | null = null;

  beforeAll(async () => {
    // Ensure we're authenticated
    await runCli(['team', 'list']);

    // Check if TFA is already enabled and disable it for clean state
    const status = await getTFAStatus();
    if (status.enabled) {
      console.warn('TFA was already enabled - cannot clean state without existing secret');
    }
  });

  afterAll(async () => {
    // Cleanup: ensure TFA is disabled after tests
    if (tfaSecret) {
      try {
        await disableTFA(tfaSecret);
      } catch {
        console.warn('Failed to cleanup TFA state after tests');
      }
    }
  });

  describe('auth tfa status', () => {
    it('should show TFA status', async () => {
      const result = await runCli(['auth', 'tfa', 'status']);

      expect(result.success).toBe(true);
      // Should contain either "enabled" or "not enabled"
      expect(result.stdout).toMatch(/enabled/i);
    });
  });

  describe('auth tfa enable', () => {
    it('should enable TFA and return a secret', async () => {
      const result = await runCli(['auth', 'tfa', 'enable']);

      if (!result.success) {
        const errorMsg = getErrorMessage(result);
        // If TFA is already enabled, that's a known state
        if (errorMsg.includes('already enabled')) {
          console.warn('Skipping test - TFA is already enabled on this account');
          return;
        }
        console.error('TFA enable failed:', errorMsg);
      }

      expect(result.success, `Failed: ${getErrorMessage(result)}`).toBe(true);

      // Extract and validate secret
      tfaSecret = extractSecret(result);
      expect(tfaSecret, 'Expected a TFA secret to be returned').not.toBeNull();
      expect(tfaSecret).toMatch(/^[A-Z2-7]{32}$/);
    });

    it('should fail when TFA is already enabled', async () => {
      // Skip if we don't have a secret (previous test didn't enable TFA)
      if (!tfaSecret) {
        console.warn('Skipping test - no TFA secret available');
        return;
      }

      const result = await runCli(['auth', 'tfa', 'enable']);

      expectError(result, { messageContains: ErrorPatterns.TFA_ALREADY_ENABLED });
    });
  });

  describe('auth tfa status (after enabling)', () => {
    it('should show TFA is enabled', async () => {
      if (!tfaSecret) {
        console.warn('Skipping test - no TFA secret available');
        return;
      }

      const result = await runCli(['auth', 'tfa', 'status']);

      expect(result.success).toBe(true);
      expect(result.stdout).toMatch(/enabled/i);
      expect(result.stdout).not.toMatch(/not enabled/i);
    });
  });

  describe('auth tfa disable', () => {
    it('should fail with invalid code', async () => {
      if (!tfaSecret) {
        console.warn('Skipping test - no TFA secret available');
        return;
      }

      const result = await runCli(['auth', 'tfa', 'disable', '--code', '000000', '--yes']);

      expectError(result, { messageContains: ErrorPatterns.TFA_INVALID_CODE });
    });

    it('should fail with wrong format code', async () => {
      if (!tfaSecret) {
        console.warn('Skipping test - no TFA secret available');
        return;
      }

      const result = await runCli(['auth', 'tfa', 'disable', '--code', 'abc123', '--yes']);

      // Should fail - either validation error or invalid code
      expect(result.success).toBe(false);
    });

    it('should succeed with valid code', async () => {
      if (!tfaSecret) {
        console.warn('Skipping test - no TFA secret available');
        return;
      }

      const code = generateTOTPCode(tfaSecret);
      const result = await runCli(['auth', 'tfa', 'disable', '--code', code, '--yes']);

      if (!result.success) {
        console.error('TFA disable failed:', getErrorMessage(result));
      }

      expect(result.success, `Failed: ${getErrorMessage(result)}`).toBe(true);
      expect(result.stdout).toContain('TFA disabled');

      tfaSecret = null; // Mark as disabled
    });
  });

  describe('auth tfa disable (when not enabled)', () => {
    it('should fail when TFA is not enabled', async () => {
      // At this point TFA should be disabled from the previous test
      const result = await runCli(['auth', 'tfa', 'disable', '--code', '123456', '--yes']);

      expectError(result, { messageContains: ErrorPatterns.TFA_NOT_ENABLED });
    });
  });

  describe('auth tfa status (after disabling)', () => {
    it('should show TFA is not enabled', async () => {
      const result = await runCli(['auth', 'tfa', 'status']);

      expect(result.success).toBe(true);
      expect(result.stdout).toMatch(/not enabled/i);
    });
  });
});
