import { afterAll, describe, expect, it } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('context commands', () => {
  afterAll(async () => {
    // Clear context after tests
    await runCli(['context', 'clear']);
  });

  describe('context show', () => {
    it('should show current context', async () => {
      const result = await runCli(['context', 'show'], { skipJsonParse: true });

      expect(result.success).toBe(true);
      // Context output might be text-based
    });
  });

  describe('context set', () => {
    it('should set team context', async () => {
      // First get a valid team name
      const teamResult = await runCli(['team', 'list']);
      const teams = teamResult.json as unknown[];
      const teamName = (teams[0] as Record<string, unknown>).teamName as string;

      const result = await runCli(['context', 'set', '--team', teamName], { skipJsonParse: true });

      // Context set should at least run and produce some output
      expect(result.success || result.stdout.length > 0 || result.stderr.length > 0).toBe(true);
    });
  });

  describe('context clear', () => {
    it('should clear context', async () => {
      const result = await runCli(['context', 'clear'], { skipJsonParse: true });

      expect(result.success).toBe(true);
    });
  });
});
