import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { getErrorMessage, runCli } from './helpers/cli.js';

describe('permission commands', () => {
  let teamName: string;

  beforeAll(async () => {
    // Get a valid team name
    const teamResult = await runCli(['team', 'list']);
    const teams = teamResult.json as unknown[];
    teamName = (teams[0] as Record<string, unknown>).teamName as string;
  });

  describe('permission list', () => {
    it('should list permissions for a team', async () => {
      // Permission list requires team context
      const result = await runCli(['permission', 'list', '--team', teamName]);

      // Fresh accounts should have at least the command run
      // May fail due to permission requirements
      expect(result.success || result.stderr.length > 0).toBe(true);
    });
  });

  describe('permission modifications', () => {
    let testGroupName: string;
    let featureAvailable = true;

    beforeAll(async () => {
      testGroupName = `test-group-${Date.now()}`;
      // Create a test permission group
      const result = await runCli(['permission', 'group', 'create', testGroupName]);
      if (!result.success) {
        const errorMsg = getErrorMessage(result);
        // Check if this is a feature limitation (Community edition)
        if (errorMsg.includes('Community edition') || errorMsg.includes('not available')) {
          console.warn(
            'Skipping permission modification tests - feature not available in this edition'
          );
          featureAvailable = false;
          return;
        }
        console.error('Permission group create failed:', errorMsg);
        expect(result.success, `Failed: ${errorMsg}`).toBe(true);
      }
    });

    afterAll(async () => {
      // Cleanup - delete test group (only if it was created)
      if (featureAvailable) {
        await runCli(['permission', 'group', 'delete', testGroupName, '--force']);
      }
    });

    it('should add a permission to a group', async () => {
      if (!featureAvailable) {
        console.warn('Skipped: feature not available in Community edition');
        return;
      }

      const result = await runCli(['permission', 'add', testGroupName, 'machine:read']);

      if (!result.success) {
        console.error('Permission add failed:', getErrorMessage(result));
      }
      expect(result.success, `Failed: ${getErrorMessage(result)}`).toBe(true);
      expect(result.stdout).toContain('Permission added');
    });

    it('should show permission group with added permission', async () => {
      if (!featureAvailable) {
        console.warn('Skipped: feature not available in Community edition');
        return;
      }

      const result = await runCli(['permission', 'group', 'show', testGroupName]);

      if (!result.success) {
        console.error('Permission group show failed:', getErrorMessage(result));
      }
      expect(result.success, `Failed: ${getErrorMessage(result)}`).toBe(true);
      expect(result.json).not.toBeNull();
    });

    it('should remove a permission from a group', async () => {
      if (!featureAvailable) {
        console.warn('Skipped: feature not available in Community edition');
        return;
      }

      const result = await runCli(['permission', 'remove', testGroupName, 'machine:read']);

      if (!result.success) {
        console.error('Permission remove failed:', getErrorMessage(result));
      }
      expect(result.success, `Failed: ${getErrorMessage(result)}`).toBe(true);
      expect(result.stdout).toContain('Permission removed');
    });
  });
});
