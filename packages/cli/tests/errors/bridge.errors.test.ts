import { describe, it, expect, beforeAll } from 'vitest';
import { runCli, getErrorMessage } from '../helpers/cli.js';
import { expectError, nonExistentName, ErrorPatterns } from '../helpers/errors.js';

/**
 * Negative test cases for bridge commands.
 * Tests backend error responses from middleware stored procedures.
 */
describe('bridge error scenarios', () => {
  let defaultRegionName: string;

  beforeAll(async () => {
    // Get default region for tests
    const regionsResult = await runCli(['region', 'list']);
    const regions = regionsResult.json as { regionName: string }[];
    defaultRegionName = regions.find((r) => r.regionName !== 'Global')?.regionName ?? 'Global';
  });

  // ============================================
  // CreateBridge Errors
  // ============================================
  describe('CreateBridge errors', () => {
    it('should fail when creating bridge with duplicate name', async () => {
      const bridgeName = `error-test-dup-${Date.now()}`;

      // Create the bridge first
      const createResult = await runCli([
        'bridge',
        'create',
        bridgeName,
        '--region',
        defaultRegionName,
      ]);
      expect(createResult.success, `Setup failed: ${getErrorMessage(createResult)}`).toBe(true);

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runCli([
          'bridge',
          'create',
          bridgeName,
          '--region',
          defaultRegionName,
        ]);
        expectError(duplicateResult, { messageContains: ErrorPatterns.BRIDGE_ALREADY_EXISTS });
      } finally {
        // Cleanup
        await runCli(['bridge', 'delete', bridgeName, '--region', defaultRegionName, '--force']);
      }
    });

    it('should fail when creating bridge in non-existent region', async () => {
      const result = await runCli([
        'bridge',
        'create',
        'test-bridge',
        '--region',
        nonExistentName('region'),
      ]);
      expectError(result, { messageContains: ErrorPatterns.REGION_NOT_FOUND });
    });
  });

  // ============================================
  // DeleteBridge Errors
  // ============================================
  describe('DeleteBridge errors', () => {
    it('should fail when deleting non-existent bridge', async () => {
      const result = await runCli([
        'bridge',
        'delete',
        nonExistentName('bridge'),
        '--region',
        defaultRegionName,
        '--force',
      ]);
      expectError(result, { messageContains: ErrorPatterns.BRIDGE_NOT_FOUND });
    });

    it('should fail when deleting bridge from non-existent region', async () => {
      const result = await runCli([
        'bridge',
        'delete',
        'some-bridge',
        '--region',
        nonExistentName('region'),
        '--force',
      ]);
      expectError(result, { messageContains: ErrorPatterns.REGION_NOT_FOUND });
    });

    it('should fail when deleting Global Bridges (system entity)', async () => {
      // Get the actual default region name and default bridge
      const regionsResult = await runCli(['region', 'list']);
      const regions = regionsResult.json as { regionName: string }[];
      const defaultRegion = regions[0]?.regionName ?? 'Default Region';

      const bridgesResult = await runCli(['bridge', 'list', '--region', defaultRegion]);
      const bridges = bridgesResult.json as { bridgeName: string }[];
      const defaultBridge = bridges.find((b) => b.bridgeName.includes('Global'))?.bridgeName;

      // Skip if no default bridge found
      if (!defaultBridge) {
        console.log('Skipping: No Global bridge found in default region');
        return;
      }

      const result = await runCli([
        'bridge',
        'delete',
        defaultBridge,
        '--region',
        defaultRegion,
        '--force',
      ]);
      expectError(result, { messageContains: ErrorPatterns.BRIDGE_CANNOT_DELETE_DEFAULT });
    });
  });

  // ============================================
  // RenameBridge Errors
  // ============================================
  describe('RenameBridge errors', () => {
    it('should fail when renaming non-existent bridge', async () => {
      const result = await runCli([
        'bridge',
        'rename',
        nonExistentName('bridge'),
        'new-name',
        '--region',
        defaultRegionName,
      ]);
      expectError(result, { messageContains: ErrorPatterns.BRIDGE_NOT_FOUND });
    });

    it('should fail when renaming bridge in non-existent region', async () => {
      const result = await runCli([
        'bridge',
        'rename',
        'some-bridge',
        'new-name',
        '--region',
        nonExistentName('region'),
      ]);
      expectError(result, { messageContains: ErrorPatterns.REGION_NOT_FOUND });
    });

    it('should fail when renaming to an existing bridge name', async () => {
      const tempBridgeName = `error-test-rename-${Date.now()}`;
      const existingBridgeName = `error-test-existing-${Date.now()}`;

      // Create two bridges
      const createResult1 = await runCli([
        'bridge',
        'create',
        tempBridgeName,
        '--region',
        defaultRegionName,
      ]);
      expect(createResult1.success, `Setup failed: ${getErrorMessage(createResult1)}`).toBe(true);

      const createResult2 = await runCli([
        'bridge',
        'create',
        existingBridgeName,
        '--region',
        defaultRegionName,
      ]);
      expect(createResult2.success, `Setup failed: ${getErrorMessage(createResult2)}`).toBe(true);

      try {
        // Try to rename temp bridge to existing bridge name - should fail
        const renameResult = await runCli([
          'bridge',
          'rename',
          tempBridgeName,
          existingBridgeName,
          '--region',
          defaultRegionName,
        ]);
        expectError(renameResult, { messageContains: ErrorPatterns.BRIDGE_ALREADY_EXISTS });
      } finally {
        // Cleanup both bridges
        await runCli([
          'bridge',
          'delete',
          tempBridgeName,
          '--region',
          defaultRegionName,
          '--force',
        ]);
        await runCli([
          'bridge',
          'delete',
          existingBridgeName,
          '--region',
          defaultRegionName,
          '--force',
        ]);
      }
    });
  });

  // ============================================
  // UpdateBridgeVault Errors
  // ============================================
  // Note: Vault update tests require --vault-version parameter which needs
  // fetching current vault version first. This is a CLI parameter requirement,
  // not a backend error test, so these tests are omitted.
});
