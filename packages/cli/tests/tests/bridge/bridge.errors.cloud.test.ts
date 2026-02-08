import { expect, test } from '@playwright/test';
import { SYSTEM_DEFAULTS } from '@rediacc/shared/config';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { ErrorPatterns, expectError, nonExistentName } from '../../src/utils/errors';

/**
 * Negative test cases for bridge commands.
 */
test.describe('Bridge Error Scenarios @cli @errors', () => {
  let runner: CliTestRunner;
  let defaultRegionName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get default region
    const regionsResult = await runner.run(['region', 'list']);
    const regions = runner.expectSuccessArray<{ regionName: string }>(regionsResult);
    defaultRegionName =
      regions.find((r) => r.regionName !== 'Global')?.regionName ?? SYSTEM_DEFAULTS.REGION_NAME;
  });

  test.describe('CreateBridge errors', () => {
    test('should fail when creating bridge with duplicate name', async () => {
      const bridgeName = `error-test-dup-${Date.now()}`;

      // Create the bridge first
      const createResult = await runner.bridgeCreate(bridgeName, defaultRegionName);
      expect(createResult.success, `Setup failed: ${runner.getErrorMessage(createResult)}`).toBe(
        true
      );

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runner.bridgeCreate(bridgeName, defaultRegionName);
        expectError(runner, duplicateResult, {
          messageContains: ErrorPatterns.BRIDGE_ALREADY_EXISTS,
        });
      } finally {
        // Cleanup
        await runner.bridgeDelete(bridgeName, defaultRegionName);
      }
    });

    test('should fail when creating bridge in non-existent region', async () => {
      const result = await runner.run([
        'bridge',
        'create',
        'test-bridge',
        '--region',
        nonExistentName('region'),
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.REGION_NOT_FOUND });
    });
  });

  test.describe('DeleteBridge errors', () => {
    test('should fail when deleting non-existent bridge', async () => {
      const result = await runner.run([
        'bridge',
        'delete',
        nonExistentName('bridge'),
        '--region',
        defaultRegionName,
        '--force',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.BRIDGE_NOT_FOUND });
    });

    test('should fail when deleting bridge from non-existent region', async () => {
      const result = await runner.run([
        'bridge',
        'delete',
        'some-bridge',
        '--region',
        nonExistentName('region'),
        '--force',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.REGION_NOT_FOUND });
    });

    test('should fail when deleting Global Bridges (system entity)', async () => {
      // Get the actual default region name and default bridge
      const regionsResult = await runner.run(['region', 'list']);
      const regions = runner.expectSuccessArray<{ regionName: string }>(regionsResult);
      const defaultRegion = regions[0]?.regionName ?? SYSTEM_DEFAULTS.REGION_NAME;

      const bridgesResult = await runner.run(['bridge', 'list', '--region', defaultRegion]);
      const bridges = runner.expectSuccessArray<{ bridgeName: string }>(bridgesResult);
      const defaultBridge = bridges.find((b) => b.bridgeName.includes('Global'))?.bridgeName;

      // Skip if no default bridge found
      if (!defaultBridge) {
        console.warn('Skipping: No Global bridge found in default region');
        return;
      }

      const result = await runner.run([
        'bridge',
        'delete',
        defaultBridge,
        '--region',
        defaultRegion,
        '--force',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.BRIDGE_CANNOT_DELETE_DEFAULT });
    });
  });

  test.describe('RenameBridge errors', () => {
    test('should fail when renaming non-existent bridge', async () => {
      const result = await runner.run([
        'bridge',
        'rename',
        nonExistentName('bridge'),
        'new-name',
        '--region',
        defaultRegionName,
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.BRIDGE_NOT_FOUND });
    });

    test('should fail when renaming bridge in non-existent region', async () => {
      const result = await runner.run([
        'bridge',
        'rename',
        'some-bridge',
        'new-name',
        '--region',
        nonExistentName('region'),
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.REGION_NOT_FOUND });
    });

    test('should fail when renaming to an existing bridge name', async () => {
      const tempBridgeName = `error-test-rename-${Date.now()}`;
      const existingBridgeName = `error-test-existing-${Date.now()}`;

      // Create two bridges
      const createResult1 = await runner.bridgeCreate(tempBridgeName, defaultRegionName);
      expect(createResult1.success, `Setup failed: ${runner.getErrorMessage(createResult1)}`).toBe(
        true
      );

      const createResult2 = await runner.bridgeCreate(existingBridgeName, defaultRegionName);
      expect(createResult2.success, `Setup failed: ${runner.getErrorMessage(createResult2)}`).toBe(
        true
      );

      try {
        // Try to rename temp bridge to existing bridge name - should fail
        const renameResult = await runner.run([
          'bridge',
          'rename',
          tempBridgeName,
          existingBridgeName,
          '--region',
          defaultRegionName,
        ]);
        expectError(runner, renameResult, { messageContains: ErrorPatterns.BRIDGE_ALREADY_EXISTS });
      } finally {
        // Cleanup both bridges
        await runner.bridgeDelete(tempBridgeName, defaultRegionName);
        await runner.bridgeDelete(existingBridgeName, defaultRegionName);
      }
    });
  });

  test.describe('RenameBridge empty name errors', () => {
    test('should fail when renaming bridge to empty name', async () => {
      const tempBridgeName = `error-test-empty-${Date.now()}`;

      // Create a temp bridge
      const createResult = await runner.bridgeCreate(tempBridgeName, defaultRegionName);
      expect(createResult.success, `Setup failed: ${runner.getErrorMessage(createResult)}`).toBe(
        true
      );

      try {
        // Try to rename to empty string - should fail
        const renameResult = await runner.run([
          'bridge',
          'rename',
          tempBridgeName,
          '',
          '--region',
          defaultRegionName,
        ]);
        expectError(runner, renameResult, { messageContains: ErrorPatterns.BRIDGE_NAME_EMPTY });
      } finally {
        // Cleanup
        await runner.bridgeDelete(tempBridgeName, defaultRegionName);
      }
    });
  });
});
