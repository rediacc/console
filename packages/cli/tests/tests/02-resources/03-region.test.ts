import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('Region Commands @cli @resources', () => {
  let runner: CliTestRunner;

  test.beforeAll(() => {
    runner = CliTestRunner.fromGlobalState();
  });

  test.describe('region list', () => {
    test('should list all regions', async () => {
      const result = await runner.regionList();

      expect(runner.isSuccess(result)).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const regions = runner.expectSuccessArray<{ regionName: string }>(result);
      if (regions.length > 0) {
        expect(regions[0]).toHaveProperty('regionName');
      }
    });
  });

  // Regions are typically read-only resources
  // Create/delete operations might not be available or require admin access
});
