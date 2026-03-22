import { expect, test } from '@playwright/test';
import { PLAN_LIMITS, type SubscriptionPlan } from '../../src/utils/edition';

/**
 * Edition Plan Limits Validation Tests
 *
 * Tests that verify plan limits are correctly defined and progressively scale
 * across subscription editions.
 */
test.describe('Plan Limits Validation @cli @edition', () => {
  test.describe('Cross-Edition Limit Comparison', () => {
    const editions: SubscriptionPlan[] = ['COMMUNITY', 'PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'];

    for (const plan of editions) {
      test(`should have limits defined for ${plan} edition`, () => {
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
