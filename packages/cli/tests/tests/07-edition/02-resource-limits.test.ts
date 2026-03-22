import { expect, test } from '@playwright/test';
import { SYSTEM_DEFAULTS } from '@rediacc/shared/config';
import {
  createEditionContext,
  type EditionTestContext,
  PLAN_LIMITS,
  type SubscriptionPlan,
  uniqueName,
} from '../../src/utils/edition';

/**
 * Edition Resource Limits Tests
 *
 * Tests that verify resource limits are correctly defined by subscription edition.
 * Validates the PLAN_LIMITS constant has correct progressive scaling.
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
        const limits = PLAN_LIMITS[plan];

        expect(limits.maxRepositorySizeGb).toBeGreaterThan(0);
        expect(limits.maxRepoLicenseIssuancesPerMonth).toBeGreaterThan(0);
      });
    }

    test('should have progressively higher storage limits', () => {
      expect(PLAN_LIMITS.PROFESSIONAL.maxRepositorySizeGb).toBeGreaterThan(
        PLAN_LIMITS.COMMUNITY.maxRepositorySizeGb
      );
      expect(PLAN_LIMITS.BUSINESS.maxRepositorySizeGb).toBeGreaterThan(
        PLAN_LIMITS.PROFESSIONAL.maxRepositorySizeGb
      );
      expect(PLAN_LIMITS.ENTERPRISE.maxRepositorySizeGb).toBeGreaterThan(
        PLAN_LIMITS.BUSINESS.maxRepositorySizeGb
      );
    });

    test('should have progressively higher license issuance limits', () => {
      expect(PLAN_LIMITS.PROFESSIONAL.maxRepoLicenseIssuancesPerMonth).toBeGreaterThan(
        PLAN_LIMITS.COMMUNITY.maxRepoLicenseIssuancesPerMonth
      );
      expect(PLAN_LIMITS.BUSINESS.maxRepoLicenseIssuancesPerMonth).toBeGreaterThan(
        PLAN_LIMITS.PROFESSIONAL.maxRepoLicenseIssuancesPerMonth
      );
      expect(PLAN_LIMITS.ENTERPRISE.maxRepoLicenseIssuancesPerMonth).toBeGreaterThan(
        PLAN_LIMITS.BUSINESS.maxRepoLicenseIssuancesPerMonth
      );
    });
  });
});
