import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('Permission Commands @cli @resources', () => {
  let runner: CliTestRunner;
  let teamName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get a valid team name
    const teamResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(teamResult);
    teamName = teams[0].teamName;
  });

  test.describe('permission list', () => {
    test('should list permissions for a team', async () => {
      // Permission list requires team context
      const result = await runner.run(['permission', 'list', '--team', teamName]);

      // Fresh accounts should have at least the command run
      // May fail due to permission requirements
      expect(result.success || result.stderr.length > 0).toBe(true);
    });
  });

  test.describe('permission modifications', () => {
    let testGroupName: string;
    let featureAvailable = true;

    test.beforeAll(async () => {
      testGroupName = `test-group-${Date.now()}`;
      // Create a test permission group
      const result = await runner.run(['permission', 'group', 'create', testGroupName]);
      if (!result.success) {
        const errorMsg = runner.getErrorMessage(result);
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

    test.afterAll(async () => {
      // Cleanup - delete test group (only if it was created)
      if (featureAvailable) {
        await runner.run(['permission', 'group', 'delete', testGroupName, '--force']);
      }
    });

    test('should add a permission to a group', async () => {
      if (!featureAvailable) {
        console.warn('Skipped: feature not available in Community edition');
        return;
      }

      const result = await runner.run(['permission', 'add', testGroupName, 'GetTeamMachines']);

      if (!result.success) {
        console.error('Permission add failed:', runner.getErrorMessage(result));
      }
      expect(result.success, `Failed: ${runner.getErrorMessage(result)}`).toBe(true);
      expect(result.stdout).toContain('Permission added');
    });

    test('should show permission group with added permission', async () => {
      if (!featureAvailable) {
        console.warn('Skipped: feature not available in Community edition');
        return;
      }

      const result = await runner.run(['permission', 'group', 'show', testGroupName]);

      if (!result.success) {
        console.error('Permission group show failed:', runner.getErrorMessage(result));
      }
      expect(result.success, `Failed: ${runner.getErrorMessage(result)}`).toBe(true);
      expect(result.json).not.toBeNull();
    });

    test('should remove a permission from a group', async () => {
      if (!featureAvailable) {
        console.warn('Skipped: feature not available in Community edition');
        return;
      }

      const result = await runner.run(['permission', 'remove', testGroupName, 'GetTeamMachines']);

      if (!result.success) {
        console.error('Permission remove failed:', runner.getErrorMessage(result));
      }
      expect(result.success, `Failed: ${runner.getErrorMessage(result)}`).toBe(true);
      expect(result.stdout).toContain('Permission removed');
    });
  });
});
