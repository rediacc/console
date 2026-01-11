import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('VS Code Commands @cli @vscode', () => {
  let runner: CliTestRunner;

  test.beforeAll(() => {
    runner = CliTestRunner.fromGlobalState();
  });

  test.describe('vscode check', () => {
    test('should check VS Code installation status', async () => {
      const result = await runner.vscodeCheck();

      // Command should always succeed (exit 0) - it reports status regardless of installation
      expect(result.exitCode).toBe(0);

      // Output should contain installation status information
      const output = result.stdout + result.stderr;
      expect(
        output.includes('VS Code') ||
          output.includes('code') ||
          output.includes('not found') ||
          output.includes('installed') ||
          output.includes('Installation')
      ).toBe(true);
    });
  });

  test.describe('vscode list', () => {
    test('should list VS Code SSH connections', async () => {
      const result = await runner.vscodeList();

      // List command should succeed
      expect(result.exitCode).toBe(0);

      // Output should be present (may be empty array or list of connections)
      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });
  });

  test.describe('vscode cleanup', () => {
    test('should cleanup all VS Code configurations with --all flag', async () => {
      const result = await runner.vscodeCleanup(true);

      // Cleanup should succeed
      expect(result.exitCode).toBe(0);

      // Should indicate cleanup completed
      const output = result.stdout + result.stderr;
      expect(
        output.includes('cleanup') ||
          output.includes('Cleanup') ||
          output.includes('removed') ||
          output.includes('Removed') ||
          output.includes('cleaned') ||
          output.includes('No') ||
          output.includes('connections')
      ).toBe(true);
    });

    test('should handle cleanup when no connections exist', async () => {
      // Run cleanup again when connections were already cleaned
      const result = await runner.vscodeCleanup(true);

      // Should still succeed (idempotent operation)
      expect(result.exitCode).toBe(0);
    });

    test('should handle cleanup of non-existent specific connection gracefully', async () => {
      const result = await runner.vscodeCleanup(false, 'non-existent-connection-name');

      // Should succeed or return appropriate message
      // The command may exit 0 with "not found" message or exit non-zero
      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });
  });

  test.describe('vscode connect (validation)', () => {
    test('should fail when no team is specified', async () => {
      // vscode connect without required args should fail with helpful error
      const result = await runner.run(['vscode', 'connect'], { skipJsonParse: true });

      // Should fail due to missing required arguments
      expect(result.exitCode).not.toBe(0);

      // Error message should mention required arguments
      const output = result.stdout + result.stderr;
      expect(
        output.includes('team') ||
          output.includes('machine') ||
          output.includes('required') ||
          output.includes('error') ||
          output.includes('Error')
      ).toBe(true);
    });

    test('should fail with non-existent machine', async () => {
      const result = await runner.run(
        ['vscode', 'connect', '--team', 'Private Team', '--machine', 'non-existent-machine-xyz'],
        { skipJsonParse: true }
      );

      // Should fail due to invalid machine
      expect(result.exitCode).not.toBe(0);
    });
  });
});
