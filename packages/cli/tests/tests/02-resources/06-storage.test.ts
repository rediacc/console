import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('Storage Commands @cli @resources', () => {
  let runner: CliTestRunner;
  let teamName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get a valid team name
    const teamResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(teamResult);
    teamName = teams[0].teamName;
  });

  test.describe('storage list', () => {
    test('should list storage configurations or indicate none exist', async () => {
      const result = await runner.storageList();

      // Storage list might return empty or an error if no storage is configured
      expect(result).toBeDefined();

      if (result.success) {
        expect(Array.isArray(result.json)).toBe(true);
      }
    });

    test('should list storage configurations for a team or indicate none exist', async () => {
      const result = await runner.run(['storage', 'list', '--team', teamName]);

      expect(result).toBeDefined();

      if (result.success) {
        expect(Array.isArray(result.json)).toBe(true);
      }
    });
  });

  test.describe('storage CRUD operations', () => {
    let testStorageName: string;
    let renamedStorageName: string;

    test.beforeAll(() => {
      const timestamp = Date.now();
      testStorageName = `test-storage-${timestamp}`;
      renamedStorageName = `test-storage-renamed-${timestamp}`;
    });

    test('should create a storage configuration', async () => {
      // Use table format for action commands that only produce success messages
      const result = await runner.run(['storage', 'create', testStorageName, '--team', teamName], {
        outputFormat: 'table',
        skipJsonParse: true,
      });

      if (!result.success) {
        console.error('Storage create failed:', runner.getErrorMessage(result));
      }
      expect(result.success, `Failed: ${runner.getErrorMessage(result)}`).toBe(true);
      expect(result.stdout).toContain('created');
    });

    test('should list storage including created storage', async () => {
      const result = await runner.run(['storage', 'list', '--team', teamName]);

      if (!result.success) {
        console.error('Storage list failed:', runner.getErrorMessage(result));
      }
      expect(result.success, `Failed: ${runner.getErrorMessage(result)}`).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const storages = runner.expectSuccessArray<{ storageName: string }>(result);
      const found = storages.some((s) => s.storageName === testStorageName);
      expect(found).toBe(true);
    });

    test('should rename a storage configuration', async () => {
      // Use table format for action commands that only produce success messages
      const result = await runner.run(
        ['storage', 'rename', testStorageName, renamedStorageName, '--team', teamName],
        { outputFormat: 'table', skipJsonParse: true }
      );

      if (!result.success) {
        console.error('Storage rename failed:', runner.getErrorMessage(result));
      }
      expect(result.success, `Failed: ${runner.getErrorMessage(result)}`).toBe(true);
      expect(result.stdout).toContain('renamed');
    });

    test('should delete a storage configuration', async () => {
      // Use table format for action commands that only produce success messages
      const result = await runner.run(
        ['storage', 'delete', renamedStorageName, '--team', teamName, '--force'],
        { outputFormat: 'table', skipJsonParse: true }
      );

      if (!result.success) {
        console.error('Storage delete failed:', runner.getErrorMessage(result));
      }
      expect(result.success, `Failed: ${runner.getErrorMessage(result)}`).toBe(true);
      expect(result.stdout).toContain('deleted');
    });
  });
});
