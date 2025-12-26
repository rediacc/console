import { describe, expect, it } from 'vitest';
import { getErrorMessage, runCli } from '../helpers/cli.js';
import { ErrorPatterns, expectError, nonExistentName } from '../helpers/errors.js';

/**
 * Negative test cases for region commands.
 * Tests backend error responses from middleware stored procedures.
 */
describe('region error scenarios', () => {
  // ============================================
  // CreateRegion Errors
  // ============================================
  describe('CreateRegion errors', () => {
    it('should fail when creating region with duplicate name', async () => {
      const regionName = `error-test-dup-${Date.now()}`;

      // Create the region first
      const createResult = await runCli(['region', 'create', regionName]);
      expect(createResult.success, `Setup failed: ${getErrorMessage(createResult)}`).toBe(true);

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runCli(['region', 'create', regionName]);
        expectError(duplicateResult, { messageContains: ErrorPatterns.REGION_ALREADY_EXISTS });
      } finally {
        // Cleanup
        await runCli(['region', 'delete', regionName, '--force']);
      }
    });
  });

  // ============================================
  // DeleteRegion Errors
  // ============================================
  describe('DeleteRegion errors', () => {
    it('should fail when deleting non-existent region', async () => {
      const result = await runCli(['region', 'delete', nonExistentName('region'), '--force']);
      expectError(result, { messageContains: ErrorPatterns.REGION_NOT_FOUND });
    });

    it('should fail when deleting Default Region (system entity)', async () => {
      const result = await runCli(['region', 'delete', 'Default Region', '--force']);
      expectError(result, { messageContains: ErrorPatterns.REGION_CANNOT_DELETE_DEFAULT });
    });
  });

  // ============================================
  // RenameRegion Errors
  // ============================================
  describe('RenameRegion errors', () => {
    it('should fail when renaming non-existent region', async () => {
      const result = await runCli(['region', 'rename', nonExistentName('region'), 'new-name']);
      expectError(result, { messageContains: ErrorPatterns.REGION_NOT_FOUND });
    });

    it('should fail when renaming Default Region (system entity)', async () => {
      const result = await runCli(['region', 'rename', 'Default Region', 'New Name']);
      expectError(result, { messageContains: ErrorPatterns.REGION_CANNOT_RENAME_DEFAULT });
    });

    it('should fail when renaming to an existing region name', async () => {
      const tempRegionName = `error-test-rename-${Date.now()}`;

      // Create a temp region
      const createResult = await runCli(['region', 'create', tempRegionName]);
      expect(createResult.success, `Setup failed: ${getErrorMessage(createResult)}`).toBe(true);

      try {
        // Try to rename temp region to "Default Region" (which exists)
        const renameResult = await runCli(['region', 'rename', tempRegionName, 'Default Region']);
        expectError(renameResult, { messageContains: ErrorPatterns.REGION_ALREADY_EXISTS });
      } finally {
        // Cleanup
        await runCli(['region', 'delete', tempRegionName, '--force']);
      }
    });
  });
});
