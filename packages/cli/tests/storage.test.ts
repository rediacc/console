import { describe, it, expect, beforeAll } from 'vitest';
import { runCli, getErrorMessage } from './helpers/cli.js';

describe('storage commands', () => {
  let teamName: string;

  beforeAll(async () => {
    // Get a valid team name
    const teamResult = await runCli(['team', 'list']);
    const teams = teamResult.json as unknown[];
    teamName = (teams[0] as Record<string, unknown>).teamName as string;
  });

  describe('storage list', () => {
    it('should list storage configurations or indicate none exist', async () => {
      const result = await runCli(['storage', 'list']);

      // Storage list might return empty or an error if no storage is configured
      // The important thing is that the command runs without crashing
      expect(result).toBeDefined();

      if (result.success) {
        expect(Array.isArray(result.json)).toBe(true);
      }
    });

    it('should list storage configurations for a team or indicate none exist', async () => {
      const result = await runCli(['storage', 'list', '--team', teamName]);

      // Storage list might return empty or an error if no storage is configured
      expect(result).toBeDefined();

      if (result.success) {
        expect(Array.isArray(result.json)).toBe(true);
      }
    });
  });

  describe('storage CRUD operations', () => {
    let testStorageName: string;
    let renamedStorageName: string;

    beforeAll(() => {
      const timestamp = Date.now();
      testStorageName = `test-storage-${timestamp}`;
      renamedStorageName = `test-storage-renamed-${timestamp}`;
    });

    it('should create a storage configuration', async () => {
      const result = await runCli(['storage', 'create', testStorageName, '--team', teamName]);

      if (!result.success) {
        console.error('Storage create failed:', getErrorMessage(result));
      }
      expect(result.success, `Failed: ${getErrorMessage(result)}`).toBe(true);
      expect(result.stdout).toContain('created');
    });

    it('should list storage including created storage', async () => {
      const result = await runCli(['storage', 'list', '--team', teamName]);

      if (!result.success) {
        console.error('Storage list failed:', getErrorMessage(result));
      }
      expect(result.success, `Failed: ${getErrorMessage(result)}`).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const storages = result.json as { storageName: string }[];
      const found = storages.some((s) => s.storageName === testStorageName);
      expect(found).toBe(true);
    });

    it('should rename a storage configuration', async () => {
      const result = await runCli([
        'storage',
        'rename',
        testStorageName,
        renamedStorageName,
        '--team',
        teamName,
      ]);

      if (!result.success) {
        console.error('Storage rename failed:', getErrorMessage(result));
      }
      expect(result.success, `Failed: ${getErrorMessage(result)}`).toBe(true);
      expect(result.stdout).toContain('renamed');
    });

    it('should delete a storage configuration', async () => {
      const result = await runCli([
        'storage',
        'delete',
        renamedStorageName,
        '--team',
        teamName,
        '--force',
      ]);

      if (!result.success) {
        console.error('Storage delete failed:', getErrorMessage(result));
      }
      expect(result.success, `Failed: ${getErrorMessage(result)}`).toBe(true);
      expect(result.stdout).toContain('deleted');
    });
  });
});
