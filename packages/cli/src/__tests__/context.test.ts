// Skip global test setup - context operations are file-only and don't need API auth
process.env.SKIP_TEST_SETUP = '1';

import { afterAll, describe, expect, it } from 'vitest';
import { runCli } from '../../tests/helpers/cli.js';
import { setTestContextName } from '../../tests/helpers/config.js';

// Clear any inherited context from previous test files (vitest reuses fork processes)
setTestContextName(null);

describe('context commands', () => {
  const timestamp = Date.now();
  const testContext1 = `test-ctx-${timestamp}-1`;
  const testContext2 = `test-ctx-${timestamp}-2`;
  const renamedContext = `test-ctx-${timestamp}-renamed`;

  afterAll(async () => {
    // Cleanup: delete test contexts
    await runCli(['context', 'delete', testContext1], { skipJsonParse: true });
    await runCli(['context', 'delete', testContext2], { skipJsonParse: true });
    await runCli(['context', 'delete', renamedContext], { skipJsonParse: true });
  });

  describe('context create', () => {
    it('should create a new context', async () => {
      const result = await runCli(
        ['context', 'create', testContext1, '--api-url', 'https://test1.example.com/api'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('created');
    });

    it('should fail if context already exists', async () => {
      const result = await runCli(
        ['context', 'create', testContext1, '--api-url', 'https://duplicate.example.com/api'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('already exists');
    });

    it('should create second context', async () => {
      const result = await runCli(
        ['context', 'create', testContext2, '--api-url', 'https://test2.example.com/api'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('created');
    });
  });

  describe('context list', () => {
    it('should list all contexts', async () => {
      const result = await runCli(['context', 'list']);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const contexts = result.json as { name: string }[];
      const names = contexts.map((c) => c.name);
      expect(names).toContain(testContext1);
      expect(names).toContain(testContext2);
    });
  });

  describe('context current', () => {
    it('should print default when no context specified', async () => {
      // Without REDIACC_CONTEXT env var or --context flag, should return "default"
      // Explicitly clear REDIACC_CONTEXT to avoid inheriting from test setup
      const result = await runCli(['context', 'current'], {
        skipJsonParse: true,
        env: { REDIACC_CONTEXT: '' },
      });

      expect(result.success).toBe(true);
      expect(result.stdout.trim()).toBe('default');
    });

    it('should print context name when specified via -C flag', async () => {
      const result = await runCli(['--context', testContext1, 'context', 'current'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(true);
      expect(result.stdout.trim()).toBe(testContext1);
    });
  });

  describe('context show', () => {
    it('should show context details when specified via -C flag', async () => {
      const result = await runCli(['--context', testContext1, 'context', 'show']);

      expect(result.success).toBe(true);
      expect(result.json).toBeDefined();

      const ctx = result.json as { name: string; apiUrl: string };
      expect(ctx.name).toBe(testContext1);
      expect(ctx.apiUrl).toContain('test1.example.com');
    });
  });

  describe('context set', () => {
    it('should set team default', async () => {
      const result = await runCli(['--context', testContext1, 'context', 'set', 'team', 'TestTeam'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('Set "team"');

      // Verify in show
      const showResult = await runCli(['--context', testContext1, 'context', 'show']);
      const ctx = showResult.json as { team: string };
      expect(ctx.team).toBe('TestTeam');
    });

    it('should set region default', async () => {
      const result = await runCli(['--context', testContext1, 'context', 'set', 'region', 'us-west'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('Set "region"');
    });

    it('should set bridge default', async () => {
      const result = await runCli(['--context', testContext1, 'context', 'set', 'bridge', 'test-bridge'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('Set "bridge"');

      // Verify in show
      const showResult = await runCli(['--context', testContext1, 'context', 'show']);
      const ctx = showResult.json as { bridge: string };
      expect(ctx.bridge).toBe('test-bridge');
    });

    it('should set machine default', async () => {
      const result = await runCli(
        ['--context', testContext1, 'context', 'set', 'machine', 'test-machine'],
        {
          skipJsonParse: true,
        }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('Set "machine"');

      // Verify in show
      const showResult = await runCli(['--context', testContext1, 'context', 'show']);
      const ctx = showResult.json as { machine: string };
      expect(ctx.machine).toBe('test-machine');
    });

    it('should fail for invalid key', async () => {
      const result = await runCli(['--context', testContext1, 'context', 'set', 'invalid-key', 'value'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('Invalid key');
    });
  });

  describe('context clear', () => {
    it('should clear specific default', async () => {
      // First set a value
      await runCli(['--context', testContext1, 'context', 'set', 'team', 'ToClear'], {
        skipJsonParse: true,
      });

      // Clear it
      const result = await runCli(['--context', testContext1, 'context', 'clear', 'team'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('Cleared');

      // Verify it's cleared
      const showResult = await runCli(['--context', testContext1, 'context', 'show']);
      const ctx = showResult.json as { team: string };
      expect(ctx.team).toBe('-');
    });

    it('should clear all defaults', async () => {
      // Set some values
      await runCli(['--context', testContext1, 'context', 'set', 'team', 'Team1'], { skipJsonParse: true });
      await runCli(['--context', testContext1, 'context', 'set', 'region', 'Region1'], {
        skipJsonParse: true,
      });

      // Clear all
      const result = await runCli(['--context', testContext1, 'context', 'clear'], { skipJsonParse: true });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('Cleared');

      // Verify all are cleared
      const showResult = await runCli(['--context', testContext1, 'context', 'show']);
      const ctx = showResult.json as { team: string; region: string };
      expect(ctx.team).toBe('-');
      expect(ctx.region).toBe('-');
    });
  });

  describe('context rename', () => {
    it('should rename a context', async () => {
      // Create a context to rename
      await runCli(
        ['context', 'create', renamedContext, '--api-url', 'https://rename.example.com/api'],
        {
          skipJsonParse: true,
        }
      );

      const newName = `${renamedContext}-new`;
      const result = await runCli(['context', 'rename', renamedContext, newName], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('renamed');

      // Verify old name doesn't exist
      const listResult = await runCli(['context', 'list']);
      const contexts = listResult.json as { name: string }[];
      const names = contexts.map((c) => c.name);
      expect(names).not.toContain(renamedContext);
      expect(names).toContain(newName);

      // Cleanup
      await runCli(['context', 'delete', newName], { skipJsonParse: true });
    });

    it('should fail if new name already exists', async () => {
      const result = await runCli(['context', 'rename', testContext1, testContext2], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('already exists');
    });
  });

  describe('context delete', () => {
    it('should delete a context', async () => {
      // Create a context to delete
      const toDelete = `test-ctx-${timestamp}-delete`;
      await runCli(['context', 'create', toDelete, '--api-url', 'https://delete.example.com/api'], {
        skipJsonParse: true,
      });

      const result = await runCli(['context', 'delete', toDelete], { skipJsonParse: true });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('deleted');

      // Verify it's gone
      const listResult = await runCli(['context', 'list']);
      const contexts = listResult.json as { name: string }[];
      const names = contexts.map((c) => c.name);
      expect(names).not.toContain(toDelete);
    });

    it('should fail for non-existent context', async () => {
      const result = await runCli(['context', 'delete', 'non-existent-ctx-xyz'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('not found');
    });
  });

  describe('global --context flag', () => {
    it('should use specified context for single command', async () => {
      // Use -C to check testContext2
      const result = await runCli(['--context', testContext2, 'context', 'show']);

      expect(result.success).toBe(true);
      const ctx = result.json as { name: string };
      expect(ctx.name).toBe(testContext2);
    });

    it('should work with different contexts in sequence', async () => {
      // Access testContext1
      const result1 = await runCli(['--context', testContext1, 'context', 'show']);
      expect(result1.success).toBe(true);
      expect((result1.json as { name: string }).name).toBe(testContext1);

      // Access testContext2
      const result2 = await runCli(['--context', testContext2, 'context', 'show']);
      expect(result2.success).toBe(true);
      expect((result2.json as { name: string }).name).toBe(testContext2);
    });
  });
});
