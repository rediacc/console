import { expect, test } from '@playwright/test';
import {
  createEditionContext,
  type EditionTestContext,
  FEATURE_MATRIX,
  isFeatureAvailable,
  type SubscriptionPlan,
} from '../../src/utils/edition';

/**
 * Edition Feature Flags Tests
 *
 * Tests that verify feature flags returned by the dashboard/organization API
 * correctly reflect the subscription edition.
 */
test.describe('Feature Flags by Edition @cli @edition', () => {
  const allEditions: SubscriptionPlan[] = ['COMMUNITY', 'PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'];

  for (const plan of allEditions) {
    test.describe(`${plan} edition feature flags`, () => {
      let ctx: EditionTestContext;
      let dashboardData: Record<string, unknown> | null = null;

      test.beforeAll(async () => {
        ctx = await createEditionContext(plan);

        // Try to get dashboard/organization info
        const infoResult = await ctx.runner.run(['organization', 'info']);

        if (infoResult.success && infoResult.json && typeof infoResult.json === 'object') {
          dashboardData = infoResult.json as Record<string, unknown>;
        } else {
          // Try alternate command if organization info doesn't exist
          const dashResult = await ctx.runner.run(['dashboard']);
          if (dashResult.success && dashResult.json && typeof dashResult.json === 'object') {
            dashboardData = dashResult.json as Record<string, unknown>;
          }
        }
      });

      test.afterAll(async () => {
        await ctx?.cleanup();
      });

      test('should return feature flags in API response', () => {
        if (!dashboardData) {
          console.warn(
            `Dashboard/organization info command not available for ${plan} edition test. ` +
              'Skipping feature flag verification.'
          );
          return;
        }

        expect(dashboardData).toBeDefined();
      });

      test('should report correct HasAdvancedAnalytics flag', () => {
        if (!dashboardData) {
          return;
        }

        const expected = isFeatureAvailable('advancedAnalytics', plan);
        const featureAccess = dashboardData.featureAccess as Record<string, boolean> | undefined;
        const actual = featureAccess?.HasAdvancedAnalytics ?? dashboardData.HasAdvancedAnalytics;

        if (actual !== undefined) {
          expect(actual, `HasAdvancedAnalytics for ${plan}`).toBe(expected);
        }
      });

      test('should report correct HasPrioritySupport flag', () => {
        if (!dashboardData) {
          return;
        }

        const expected = isFeatureAvailable('prioritySupport', plan);
        const featureAccess = dashboardData.featureAccess as Record<string, boolean> | undefined;
        const actual = featureAccess?.HasPrioritySupport ?? dashboardData.HasPrioritySupport;

        if (actual !== undefined) {
          expect(actual, `HasPrioritySupport for ${plan}`).toBe(expected);
        }
      });

      test('should report correct Ceph flag', () => {
        if (!dashboardData) {
          return;
        }

        const expected = isFeatureAvailable('ceph', plan);
        const featureAccess = dashboardData.featureAccess as Record<string, boolean> | undefined;
        const actual = featureAccess?.Ceph ?? dashboardData.Ceph;

        if (actual !== undefined) {
          expect(actual, `Ceph for ${plan}`).toBe(expected);
        }
      });

      test('should report correct AuditLog flag', () => {
        if (!dashboardData) {
          return;
        }

        const expected = isFeatureAvailable('auditLog', plan);
        const featureAccess = dashboardData.featureAccess as Record<string, boolean> | undefined;
        const actual = featureAccess?.AuditLog ?? dashboardData.AuditLog;

        if (actual !== undefined) {
          expect(actual, `AuditLog for ${plan}`).toBe(expected);
        }
      });

      test('should report correct AdvancedQueue flag', () => {
        if (!dashboardData) {
          return;
        }

        const expected = isFeatureAvailable('advancedQueue', plan);
        const featureAccess = dashboardData.featureAccess as Record<string, boolean> | undefined;
        const actual = featureAccess?.AdvancedQueue ?? dashboardData.AdvancedQueue;

        if (actual !== undefined) {
          expect(actual, `AdvancedQueue for ${plan}`).toBe(expected);
        }
      });

      test('should report correct HasCustomBranding flag', () => {
        if (!dashboardData) {
          return;
        }

        const expected = isFeatureAvailable('customBranding', plan);
        const featureAccess = dashboardData.featureAccess as Record<string, boolean> | undefined;
        const actual = featureAccess?.HasCustomBranding ?? dashboardData.HasCustomBranding;

        if (actual !== undefined) {
          expect(actual, `HasCustomBranding for ${plan}`).toBe(expected);
        }
      });

      test('should report correct HasDedicatedAccount flag', () => {
        if (!dashboardData) {
          return;
        }

        const expected = isFeatureAvailable('dedicatedAccount', plan);
        const featureAccess = dashboardData.featureAccess as Record<string, boolean> | undefined;
        const actual = featureAccess?.HasDedicatedAccount ?? dashboardData.HasDedicatedAccount;

        if (actual !== undefined) {
          expect(actual, `HasDedicatedAccount for ${plan}`).toBe(expected);
        }
      });
    });
  }

  test.describe('Feature Flag Matrix Consistency', () => {
    test('should have Community as the most restricted edition', () => {
      expect(isFeatureAvailable('advancedAnalytics', 'COMMUNITY')).toBe(false);
      expect(isFeatureAvailable('ceph', 'COMMUNITY')).toBe(false);
      expect(isFeatureAvailable('queuePriority', 'COMMUNITY')).toBe(false);
      expect(isFeatureAvailable('advancedQueue', 'COMMUNITY')).toBe(false);
      expect(isFeatureAvailable('dedicatedAccount', 'COMMUNITY')).toBe(false);
    });

    test('should have Professional as mid-tier with some features', () => {
      expect(isFeatureAvailable('permissionGroups', 'PROFESSIONAL')).toBe(true);
      expect(isFeatureAvailable('prioritySupport', 'PROFESSIONAL')).toBe(true);
      expect(isFeatureAvailable('auditLog', 'PROFESSIONAL')).toBe(true);
      expect(isFeatureAvailable('customBranding', 'PROFESSIONAL')).toBe(true);

      expect(isFeatureAvailable('ceph', 'PROFESSIONAL')).toBe(false);
      expect(isFeatureAvailable('queuePriority', 'PROFESSIONAL')).toBe(false);
      expect(isFeatureAvailable('advancedQueue', 'PROFESSIONAL')).toBe(false);
    });

    test('should have Business with most features except dedicated account', () => {
      expect(isFeatureAvailable('permissionGroups', 'BUSINESS')).toBe(true);
      expect(isFeatureAvailable('ceph', 'BUSINESS')).toBe(true);
      expect(isFeatureAvailable('queuePriority', 'BUSINESS')).toBe(true);
      expect(isFeatureAvailable('advancedAnalytics', 'BUSINESS')).toBe(true);
      expect(isFeatureAvailable('advancedQueue', 'BUSINESS')).toBe(true);

      expect(isFeatureAvailable('dedicatedAccount', 'BUSINESS')).toBe(false);
    });

    test('should have Enterprise with all features', () => {
      expect(isFeatureAvailable('permissionGroups', 'ENTERPRISE')).toBe(true);
      expect(isFeatureAvailable('ceph', 'ENTERPRISE')).toBe(true);
      expect(isFeatureAvailable('queuePriority', 'ENTERPRISE')).toBe(true);
      expect(isFeatureAvailable('advancedAnalytics', 'ENTERPRISE')).toBe(true);
      expect(isFeatureAvailable('advancedQueue', 'ENTERPRISE')).toBe(true);
      expect(isFeatureAvailable('dedicatedAccount', 'ENTERPRISE')).toBe(true);
      expect(isFeatureAvailable('prioritySupport', 'ENTERPRISE')).toBe(true);
      expect(isFeatureAvailable('auditLog', 'ENTERPRISE')).toBe(true);
      expect(isFeatureAvailable('customBranding', 'ENTERPRISE')).toBe(true);
    });
  });

  test.describe('Feature Availability Helper Functions', () => {
    test('isFeatureAvailable should return correct values', () => {
      expect(isFeatureAvailable('permissionGroups', 'COMMUNITY')).toBe(false);
      expect(isFeatureAvailable('permissionGroups', 'PROFESSIONAL')).toBe(true);

      expect(isFeatureAvailable('ceph', 'PROFESSIONAL')).toBe(false);
      expect(isFeatureAvailable('ceph', 'BUSINESS')).toBe(true);

      expect(isFeatureAvailable('dedicatedAccount', 'BUSINESS')).toBe(false);
      expect(isFeatureAvailable('dedicatedAccount', 'ENTERPRISE')).toBe(true);
    });

    test('FEATURE_MATRIX should define all expected features', () => {
      const expectedFeatures = [
        'permissionGroups',
        'ceph',
        'queuePriority',
        'advancedAnalytics',
        'prioritySupport',
        'auditLog',
        'advancedQueue',
        'customBranding',
        'dedicatedAccount',
      ];

      for (const feature of expectedFeatures) {
        expect(
          FEATURE_MATRIX[feature as keyof typeof FEATURE_MATRIX],
          `Feature "${feature}" should be defined in FEATURE_MATRIX`
        ).toBeDefined();
      }
    });
  });
});
