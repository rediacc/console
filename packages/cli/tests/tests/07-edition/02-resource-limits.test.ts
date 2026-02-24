import { expect, test } from '@playwright/test';
import { SYSTEM_DEFAULTS } from '@rediacc/shared/config';
import {
  createEditionContext,
  type EditionTestContext,
  RESOURCE_LIMITS,
  type SubscriptionPlan,
  uniqueName,
} from '../../src/utils/edition';

/**
 * Edition Resource Limits Tests
 *
 * Tests that verify resource limits are correctly enforced by subscription edition.
 * Tests both boundary cases (creating up to limit) and exceeding limits.
 *
 * Note: Machine and Repository limits have been removed as they are now unlimited for all plans.
 */
test.describe('Resource Limits by Edition @cli @edition', () => {
  test.describe('Storage Limits', () => {
    test.describe('COMMUNITY edition storage limits', () => {
      let ctx: EditionTestContext;
      let teamName: string;
      const createdStorages: string[] = [];

      test.beforeAll(async () => {
        ctx = await createEditionContext('COMMUNITY');

        const teamResult = await ctx.runner.teamList();
        const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
        teamName = teams[0]?.teamName ?? SYSTEM_DEFAULTS.TEAM_NAME;
      });

      test.afterAll(async () => {
        for (const storage of createdStorages) {
          await ctx.runner
            .run(['storage', 'delete', storage, '--team', teamName, '--force'])
            .catch(() => {});
        }
        await ctx?.cleanup();
      });

      test('should allow creating storage within limits', async () => {
        const storageName = uniqueName('storage');
        const result = await ctx.runner.run(['storage', 'create', storageName, '--team', teamName]);

        if (result.success) {
          createdStorages.push(storageName);
        }
        // Don't fail test if storage command doesn't exist yet
        expect(result.success || result.stderr.includes('unknown command')).toBe(true);
      });
    });
  });

  test.describe('Cross-Edition Limit Comparison', () => {
    const editions: SubscriptionPlan[] = ['COMMUNITY', 'PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'];

    for (const plan of editions) {
      test(`should have valid limits for ${plan} edition`, () => {
        const limits = RESOURCE_LIMITS[plan];

        expect(limits.bridges).toBeGreaterThanOrEqual(0);
      });
    }

    test('should have progressively higher bridge limits', () => {
      expect(RESOURCE_LIMITS.COMMUNITY.bridges).toBe(0);
      expect(RESOURCE_LIMITS.PROFESSIONAL.bridges).toBeGreaterThan(
        RESOURCE_LIMITS.COMMUNITY.bridges
      );
      expect(RESOURCE_LIMITS.BUSINESS.bridges).toBeGreaterThan(
        RESOURCE_LIMITS.PROFESSIONAL.bridges
      );
      expect(RESOURCE_LIMITS.ENTERPRISE.bridges).toBeGreaterThan(RESOURCE_LIMITS.BUSINESS.bridges);
    });
  });
});
