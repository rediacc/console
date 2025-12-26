import { describe, expect, it } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('region commands', () => {
  describe('region list', () => {
    it('should list all regions', async () => {
      const result = await runCli(['region', 'list']);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const regions = result.json as unknown[];
      if (regions.length > 0) {
        const region = regions[0] as Record<string, unknown>;
        expect(region).toHaveProperty('regionName');
      }
    });
  });

  // Regions are typically read-only resources
  // Create/delete operations might not be available or require admin access
});
