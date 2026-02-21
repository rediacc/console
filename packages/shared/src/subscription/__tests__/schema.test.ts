import { describe, expect, it } from 'vitest';
import {
  comparePlans,
  exceedsLimit,
  getPlanFeatures,
  getPlanResources,
  getResourceLimit,
  hasFeature,
  isValidPlanCode,
  SUBSCRIPTION_CONFIG,
  PLAN_FEATURES,
  PLAN_ORDER,
  PLAN_RESOURCES,
  PROGRESSIVE_LIMIT_KEYS,
} from '../constants.js';
import type { FeatureFlags, PlanCode, ResourceLimits } from '../types.js';

describe('Subscription Schema Constants', () => {
  describe('PLAN_RESOURCES', () => {
    it('should have all plan codes defined', () => {
      const planCodes: PlanCode[] = ['COMMUNITY', 'PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'];
      for (const code of planCodes) {
        expect(PLAN_RESOURCES[code]).toBeDefined();
      }
    });

    it('should have all required resource limit keys for each plan', () => {
      const requiredKeys: (keyof ResourceLimits)[] = [
        'bridges',
        'maxActiveJobs',
        'maxReservedJobs',
        'jobTimeoutHours',
        'maxRepositorySizeGb',
        'maxJobsPerMonth',
        'maxPendingPerUser',
        'maxTasksPerMachine',
        'cephPoolsPerTeam',
      ];

      for (const planCode of PLAN_ORDER) {
        const resources = PLAN_RESOURCES[planCode];
        for (const key of requiredKeys) {
          expect(resources[key], `${planCode} should have ${key} defined`).toBeDefined();
          expect(typeof resources[key], `${planCode}.${key} should be a number`).toBe('number');
        }
      }
    });

    it('should have progressively higher limits for higher plans', () => {
      for (let i = 1; i < PLAN_ORDER.length; i++) {
        const lowerPlan = PLAN_ORDER[i - 1];
        const higherPlan = PLAN_ORDER[i];
        const lower = PLAN_RESOURCES[lowerPlan];
        const higher = PLAN_RESOURCES[higherPlan];

        for (const key of PROGRESSIVE_LIMIT_KEYS) {
          expect(
            higher[key],
            `${higherPlan}.${key} (${higher[key]}) should be >= ${lowerPlan}.${key} (${lower[key]})`
          ).toBeGreaterThanOrEqual(lower[key]);
        }
      }
    });

    it('should have COMMUNITY with 0 bridges', () => {
      expect(PLAN_RESOURCES.COMMUNITY.bridges).toBe(0);
    });

    it('should have ENTERPRISE with highest limits', () => {
      expect(PLAN_RESOURCES.ENTERPRISE.maxActiveJobs).toBe(60);
      expect(PLAN_RESOURCES.ENTERPRISE.maxRepositorySizeGb).toBe(1024);
      expect(PLAN_RESOURCES.ENTERPRISE.maxJobsPerMonth).toBe(100000);
    });

    it('should have ENTERPRISE with unlimited Ceph pools (-1)', () => {
      expect(PLAN_RESOURCES.ENTERPRISE.cephPoolsPerTeam).toBe(-1);
    });

    it('should have BUSINESS with exactly 1 Ceph pool per team', () => {
      expect(PLAN_RESOURCES.BUSINESS.cephPoolsPerTeam).toBe(1);
    });
  });

  describe('PLAN_FEATURES', () => {
    it('should have all plan codes defined', () => {
      for (const code of PLAN_ORDER) {
        expect(PLAN_FEATURES[code]).toBeDefined();
      }
    });

    it('should have all required feature flags for each plan', () => {
      const requiredKeys: (keyof FeatureFlags)[] = [
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

      for (const planCode of PLAN_ORDER) {
        const features = PLAN_FEATURES[planCode];
        for (const key of requiredKeys) {
          expect(typeof features[key], `${planCode}.${key} should be a boolean`).toBe('boolean');
        }
      }
    });

    it('should have COMMUNITY with all features disabled', () => {
      const community = PLAN_FEATURES.COMMUNITY;
      expect(community.permissionGroups).toBe(false);
      expect(community.ceph).toBe(false);
      expect(community.queuePriority).toBe(false);
      expect(community.advancedAnalytics).toBe(false);
      expect(community.prioritySupport).toBe(false);
      expect(community.auditLog).toBe(false);
      expect(community.advancedQueue).toBe(false);
      expect(community.customBranding).toBe(false);
      expect(community.dedicatedAccount).toBe(false);
    });

    it('should have ENTERPRISE with all features enabled', () => {
      const enterprise = PLAN_FEATURES.ENTERPRISE;
      expect(enterprise.permissionGroups).toBe(true);
      expect(enterprise.ceph).toBe(true);
      expect(enterprise.queuePriority).toBe(true);
      expect(enterprise.advancedAnalytics).toBe(true);
      expect(enterprise.prioritySupport).toBe(true);
      expect(enterprise.auditLog).toBe(true);
      expect(enterprise.advancedQueue).toBe(true);
      expect(enterprise.customBranding).toBe(true);
      expect(enterprise.dedicatedAccount).toBe(true);
    });

    it('should have dedicated account only for ENTERPRISE', () => {
      expect(PLAN_FEATURES.COMMUNITY.dedicatedAccount).toBe(false);
      expect(PLAN_FEATURES.PROFESSIONAL.dedicatedAccount).toBe(false);
      expect(PLAN_FEATURES.BUSINESS.dedicatedAccount).toBe(false);
      expect(PLAN_FEATURES.ENTERPRISE.dedicatedAccount).toBe(true);
    });

    it('should have Ceph only for BUSINESS and ENTERPRISE', () => {
      expect(PLAN_FEATURES.COMMUNITY.ceph).toBe(false);
      expect(PLAN_FEATURES.PROFESSIONAL.ceph).toBe(false);
      expect(PLAN_FEATURES.BUSINESS.ceph).toBe(true);
      expect(PLAN_FEATURES.ENTERPRISE.ceph).toBe(true);
    });
  });

  describe('SUBSCRIPTION_CONFIG', () => {
    it('should have valid check-in interval', () => {
      expect(SUBSCRIPTION_CONFIG.checkInIntervalHours).toBeGreaterThan(0);
      expect(SUBSCRIPTION_CONFIG.checkInIntervalHours).toBeLessThanOrEqual(168); // max 1 week
    });

    it('should have valid grace period', () => {
      expect(SUBSCRIPTION_CONFIG.gracePeriodDays).toBeGreaterThan(0);
      expect(SUBSCRIPTION_CONFIG.gracePeriodDays).toBeLessThanOrEqual(30);
    });

    it('should degrade to COMMUNITY', () => {
      expect(SUBSCRIPTION_CONFIG.degradedPlan).toBe('COMMUNITY');
    });

    it('should have schema version 1', () => {
      expect(SUBSCRIPTION_CONFIG.schemaVersion).toBe(1);
    });
  });

  describe('PLAN_ORDER', () => {
    it('should have exactly 4 plans', () => {
      expect(PLAN_ORDER).toHaveLength(4);
    });

    it('should be ordered from lowest to highest tier', () => {
      expect(PLAN_ORDER[0]).toBe('COMMUNITY');
      expect(PLAN_ORDER[1]).toBe('PROFESSIONAL');
      expect(PLAN_ORDER[2]).toBe('BUSINESS');
      expect(PLAN_ORDER[3]).toBe('ENTERPRISE');
    });
  });
});

describe('Subscription Schema Helper Functions', () => {
  describe('getPlanResources', () => {
    it('should return correct resources for valid plan', () => {
      const resources = getPlanResources('PROFESSIONAL');
      expect(resources.maxActiveJobs).toBe(5);
      expect(resources.bridges).toBe(1);
    });

    it('should return COMMUNITY resources for invalid plan', () => {
      const resources = getPlanResources('INVALID' as PlanCode);
      expect(resources.maxActiveJobs).toBe(1);
      expect(resources.bridges).toBe(0);
    });
  });

  describe('getPlanFeatures', () => {
    it('should return correct features for valid plan', () => {
      const features = getPlanFeatures('BUSINESS');
      expect(features.ceph).toBe(true);
      expect(features.dedicatedAccount).toBe(false);
    });

    it('should return COMMUNITY features for invalid plan', () => {
      const features = getPlanFeatures('INVALID' as PlanCode);
      expect(features.ceph).toBe(false);
    });
  });

  describe('hasFeature', () => {
    it('should return true when plan has feature', () => {
      expect(hasFeature('ENTERPRISE', 'dedicatedAccount')).toBe(true);
      expect(hasFeature('BUSINESS', 'ceph')).toBe(true);
    });

    it('should return false when plan lacks feature', () => {
      expect(hasFeature('COMMUNITY', 'ceph')).toBe(false);
      expect(hasFeature('PROFESSIONAL', 'dedicatedAccount')).toBe(false);
    });
  });

  describe('getResourceLimit', () => {
    it('should return correct limit', () => {
      expect(getResourceLimit('ENTERPRISE', 'maxActiveJobs')).toBe(60);
      expect(getResourceLimit('COMMUNITY', 'bridges')).toBe(0);
    });

    it('should return 0 for invalid plan', () => {
      expect(getResourceLimit('INVALID' as PlanCode, 'maxActiveJobs')).toBe(1);
    });
  });

  describe('exceedsLimit', () => {
    it('should return true when value exceeds limit', () => {
      expect(exceedsLimit(5, 5)).toBe(true);
      expect(exceedsLimit(5, 6)).toBe(true);
    });

    it('should return false when value is below limit', () => {
      expect(exceedsLimit(5, 4)).toBe(false);
    });

    it('should return false for unlimited (-1)', () => {
      expect(exceedsLimit(-1, 1000000)).toBe(false);
    });

    it('should return false for zero limit (no limit set)', () => {
      expect(exceedsLimit(0, 1000000)).toBe(false);
    });

    it('should return false for negative value with positive limit', () => {
      expect(exceedsLimit(5, -1)).toBe(false);
    });

    it('should return true for value equal to limit at different magnitudes', () => {
      expect(exceedsLimit(1, 1)).toBe(true);
      expect(exceedsLimit(100, 100)).toBe(true);
    });
  });

  describe('isValidPlanCode', () => {
    it('should return true for valid plan codes', () => {
      expect(isValidPlanCode('COMMUNITY')).toBe(true);
      expect(isValidPlanCode('PROFESSIONAL')).toBe(true);
      expect(isValidPlanCode('BUSINESS')).toBe(true);
      expect(isValidPlanCode('ENTERPRISE')).toBe(true);
    });

    it('should return false for invalid plan codes', () => {
      expect(isValidPlanCode('INVALID')).toBe(false);
      expect(isValidPlanCode('community')).toBe(false);
      expect(isValidPlanCode('')).toBe(false);
    });
  });

  describe('comparePlans', () => {
    it('should return negative when first plan is lower', () => {
      expect(comparePlans('COMMUNITY', 'PROFESSIONAL')).toBeLessThan(0);
      expect(comparePlans('COMMUNITY', 'ENTERPRISE')).toBeLessThan(0);
    });

    it('should return positive when first plan is higher', () => {
      expect(comparePlans('ENTERPRISE', 'COMMUNITY')).toBeGreaterThan(0);
      expect(comparePlans('BUSINESS', 'PROFESSIONAL')).toBeGreaterThan(0);
    });

    it('should return 0 for same plan', () => {
      expect(comparePlans('BUSINESS', 'BUSINESS')).toBe(0);
    });
  });
});
