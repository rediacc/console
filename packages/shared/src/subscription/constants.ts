/**
 * Subscription Constants
 *
 * Single source of truth for plan resources and features.
 * All components (account-server, middleware, renet, CLI) should use these values.
 */

import type { FeatureFlags, PlanCode, ResourceLimits } from './types';

/**
 * Resource limits by plan.
 * This is the canonical source of truth for all plan limits.
 */
export const PLAN_RESOURCES: Record<PlanCode, ResourceLimits> = {
  COMMUNITY: {
    bridges: 0,
    maxActiveJobs: 1,
    maxReservedJobs: 1,
    jobTimeoutHours: 2,
    maxRepositorySizeGb: 10,
    maxJobsPerMonth: 500,
    maxPendingPerUser: 5,
    maxTasksPerMachine: 1,
    cephPoolsPerTeam: 0,
  },
  PROFESSIONAL: {
    bridges: 1,
    maxActiveJobs: 5,
    maxReservedJobs: 2,
    jobTimeoutHours: 24,
    maxRepositorySizeGb: 100,
    maxJobsPerMonth: 5000,
    maxPendingPerUser: 10,
    maxTasksPerMachine: 2,
    cephPoolsPerTeam: 0,
  },
  BUSINESS: {
    bridges: 2,
    maxActiveJobs: 20,
    maxReservedJobs: 3,
    jobTimeoutHours: 72,
    maxRepositorySizeGb: 500,
    maxJobsPerMonth: 20000,
    maxPendingPerUser: 20,
    maxTasksPerMachine: 3,
    cephPoolsPerTeam: 1,
  },
  ENTERPRISE: {
    bridges: 10,
    maxActiveJobs: 60,
    maxReservedJobs: 5,
    jobTimeoutHours: 96,
    maxRepositorySizeGb: 1024,
    maxJobsPerMonth: 100000,
    maxPendingPerUser: 50,
    maxTasksPerMachine: 5,
    cephPoolsPerTeam: -1, // Unlimited
  },
} as const;

/**
 * Feature availability by plan.
 */
export const PLAN_FEATURES: Record<PlanCode, FeatureFlags> = {
  COMMUNITY: {
    permissionGroups: false,
    ceph: false,
    queuePriority: false,
    advancedAnalytics: false,
    prioritySupport: false,
    auditLog: false,
    advancedQueue: false,
    customBranding: false,
    dedicatedAccount: false,
  },
  PROFESSIONAL: {
    permissionGroups: true,
    ceph: false,
    queuePriority: false,
    advancedAnalytics: false,
    prioritySupport: true,
    auditLog: true,
    advancedQueue: false,
    customBranding: true,
    dedicatedAccount: false,
  },
  BUSINESS: {
    permissionGroups: true,
    ceph: true,
    queuePriority: true,
    advancedAnalytics: true,
    prioritySupport: true,
    auditLog: true,
    advancedQueue: true,
    customBranding: true,
    dedicatedAccount: false,
  },
  ENTERPRISE: {
    permissionGroups: true,
    ceph: true,
    queuePriority: true,
    advancedAnalytics: true,
    prioritySupport: true,
    auditLog: true,
    advancedQueue: true,
    customBranding: true,
    dedicatedAccount: true,
  },
} as const;

/**
 * Subscription configuration constants.
 */
export const SUBSCRIPTION_CONFIG = {
  /** How often clients should check in with account server (hours) */
  checkInIntervalHours: 24,
  /** Days of grace period before degradation */
  gracePeriodDays: 3,
  /** Plan to degrade to when grace period expires */
  degradedPlan: 'COMMUNITY' as PlanCode,
  /** Current subscription schema version */
  schemaVersion: 1,
} as const;

/**
 * All valid plan codes in order from lowest to highest tier.
 */
export const PLAN_ORDER: readonly PlanCode[] = [
  'COMMUNITY',
  'PROFESSIONAL',
  'BUSINESS',
  'ENTERPRISE',
] as const;

/**
 * Resource limit keys that should increase with higher plans.
 * Used for validation tests.
 */
export const PROGRESSIVE_LIMIT_KEYS: readonly (keyof ResourceLimits)[] = [
  'maxActiveJobs',
  'maxReservedJobs',
  'jobTimeoutHours',
  'maxRepositorySizeGb',
  'maxJobsPerMonth',
  'maxPendingPerUser',
] as const;

/**
 * Get resources for a plan code.
 * Returns COMMUNITY resources if plan code is invalid.
 */
export function getPlanResources(planCode: string): ResourceLimits {
  if (planCode in PLAN_RESOURCES) {
    return PLAN_RESOURCES[planCode as PlanCode];
  }
  return PLAN_RESOURCES.COMMUNITY;
}

/**
 * Get features for a plan code.
 * Returns COMMUNITY features if plan code is invalid.
 */
export function getPlanFeatures(planCode: string): FeatureFlags {
  if (planCode in PLAN_FEATURES) {
    return PLAN_FEATURES[planCode as PlanCode];
  }
  return PLAN_FEATURES.COMMUNITY;
}

/**
 * Check if a plan has access to a specific feature.
 */
export function hasFeature(planCode: string, feature: keyof FeatureFlags): boolean {
  const features = getPlanFeatures(planCode);
  return features[feature];
}

/**
 * Get resource limit for a plan.
 * Returns 0 if limit not found.
 */
export function getResourceLimit(planCode: string, resource: keyof ResourceLimits): number {
  const resources = getPlanResources(planCode);
  return resources[resource];
}

/**
 * Check if a value exceeds a resource limit.
 * Returns false if limit is -1 (unlimited) or 0 (none/unlimited in some contexts).
 */
export function exceedsLimit(limit: number, value: number): boolean {
  if (limit <= 0) {
    // -1 = unlimited, 0 = no limit set
    return false;
  }
  return value >= limit;
}

/**
 * Check if a plan code is valid.
 */
export function isValidPlanCode(code: string): code is PlanCode {
  return PLAN_ORDER.includes(code as PlanCode);
}

/**
 * Compare two plan codes.
 * Returns negative if a < b, 0 if equal, positive if a > b.
 */
export function comparePlans(a: PlanCode, b: PlanCode): number {
  return PLAN_ORDER.indexOf(a) - PLAN_ORDER.indexOf(b);
}
