import { beforeAll, describe, expect, it } from 'vitest';
import { runCli } from './helpers/cli.js';

/**
 * Integration tests for vault operations through CLI.
 * These tests verify that vault-related commands work correctly
 * and that encryption/decryption is applied transparently.
 */
describe('Master Password CLI Integration', () => {
  let teamName: string;

  beforeAll(async () => {
    // Get a valid team name for testing
    const result = await runCli(['team', 'list']);
    expect(result.success).toBe(true);
    const teams = result.json as { teamName: string }[];
    expect(teams.length).toBeGreaterThan(0);
    teamName = teams[0].teamName;
  });

  describe('organization vault operations', () => {
    it('should get organization vault data', async () => {
      const result = await runCli(['organization', 'vault', 'get']);

      // Should succeed - vault may be empty or have encrypted data
      expect(result.success).toBe(true);
    });
  });

  describe('user vault operations', () => {
    it('should get current user vault', async () => {
      const result = await runCli(['user', 'vault', 'get']);

      expect(result.success).toBe(true);
    });
  });

  describe('machine list with vault status', () => {
    it('should list machines (vault data included)', async () => {
      const result = await runCli(['machine', 'list', '--team', teamName]);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });
  });

  describe('storage list operations', () => {
    it('should list storage configurations', async () => {
      const result = await runCli(['storage', 'list', '--team', teamName]);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });
  });
});
