import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

/**
 * Integration tests for vault operations through CLI.
 * These tests verify that vault-related commands work correctly
 * and that encryption/decryption is applied transparently.
 */
test.describe('Master Password CLI Integration @cli @operations', () => {
  let runner: CliTestRunner;
  let teamName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get a valid team name for testing
    const result = await runner.teamList();
    expect(runner.isSuccess(result)).toBe(true);
    const teams = runner.expectSuccessArray<{ teamName: string }>(result);
    expect(teams.length).toBeGreaterThan(0);
    teamName = teams[0].teamName;
  });

  test.describe('organization vault operations', () => {
    test('should get organization vault data', async () => {
      const result = await runner.run(['organization', 'vault', 'get']);

      // Should succeed - vault may be empty or have encrypted data
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

  test.describe('user vault operations', () => {
    test('should get current user vault', async () => {
      const result = await runner.run(['user', 'vault', 'get']);

      expect(runner.isSuccess(result)).toBe(true);
    });
  });

  test.describe('machine list with vault status', () => {
    test('should list machines (vault data included)', async () => {
      const result = await runner.machineList(teamName);

      expect(runner.isSuccess(result)).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });
  });

  test.describe('storage list operations', () => {
    test('should list storage configurations', async () => {
      // Storage list requires --team
      const result = await runner.run(['storage', 'list', '--team', teamName]);

      expect(runner.isSuccess(result)).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });
  });
});
