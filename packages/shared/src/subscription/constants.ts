/**
 * Subscription Constants
 *
 * Single source of truth for plan resources and features.
 * All components (account-server, middleware, renet, CLI) should use these values.
 */

import type {
  BillingPeriod,
  FeatureFlags,
  PlanCode,
  PlanMetadata,
  PlanPricing,
  ResourceLimits,
} from './types';

/**
 * Resource limits by plan.
 * This is the canonical source of truth for all plan limits.
 */
export const PLAN_RESOURCES: Record<PlanCode, ResourceLimits> = {
  COMMUNITY: {
    bridges: 0,
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
    maxReservedJobs: 5,
    jobTimeoutHours: 96,
    maxRepositorySizeGb: 2048,
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
 * Maximum machines allowed per plan.
 */
export const PLAN_MAX_MACHINES: Record<PlanCode, number> = {
  COMMUNITY: 2,
  PROFESSIONAL: 5,
  BUSINESS: 20,
  ENTERPRISE: 50,
} as const;

/**
 * Get maximum machines for a plan code.
 * Returns COMMUNITY limit if plan code is invalid.
 */
export function getMaxMachines(planCode: string): number {
  if (planCode in PLAN_MAX_MACHINES) {
    return PLAN_MAX_MACHINES[planCode as PlanCode];
  }
  return PLAN_MAX_MACHINES.COMMUNITY;
}

/**
 * Resource limit keys that should increase with higher plans.
 * Used for validation tests.
 */
export const PROGRESSIVE_LIMIT_KEYS: readonly (keyof ResourceLimits)[] = [
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

// =============================================================================
// PRICING
// =============================================================================

/**
 * Pricing by plan. Amounts in cents (USD).
 * Annual prices reflect a 10-month rate (2 months free).
 */
export const PLAN_PRICING: Record<PlanCode, PlanPricing> = {
  COMMUNITY: {
    monthlyPriceCents: 0,
    annualPriceCents: 0,
    currency: 'usd',
  },
  PROFESSIONAL: {
    monthlyPriceCents: 34_900,
    annualPriceCents: 349_000,
    currency: 'usd',
  },
  BUSINESS: {
    monthlyPriceCents: 69_900,
    annualPriceCents: 699_000,
    currency: 'usd',
  },
  ENTERPRISE: {
    monthlyPriceCents: 210_000,
    annualPriceCents: 2_100_000,
    currency: 'usd',
  },
} as const;

/**
 * Display metadata by plan.
 */
export const PLAN_METADATA: Record<PlanCode, PlanMetadata> = {
  COMMUNITY: {
    displayName: 'Community',
    description: 'Free for individuals and small projects',
    paid: false,
    featured: true,
  },
  PROFESSIONAL: {
    displayName: 'Professional',
    description: 'For growing teams that need more power and flexibility',
    paid: true,
    featured: false,
  },
  BUSINESS: {
    displayName: 'Business',
    description: 'For organizations that need advanced management and compliance',
    paid: true,
    featured: false,
  },
  ENTERPRISE: {
    displayName: 'Enterprise',
    description: 'For large organizations with custom infrastructure requirements',
    paid: true,
    featured: false,
  },
} as const;

/**
 * Get the Stripe lookup key for a plan and billing period.
 * E.g. "professional_monthly", "business_annual"
 */
export function getStripeLookupKey(planCode: PlanCode, period: BillingPeriod): string {
  return `${planCode.toLowerCase()}_${period}`;
}

/**
 * Get pricing for a plan code.
 * Returns COMMUNITY pricing if plan code is invalid.
 */
export function getPlanPricing(planCode: string): PlanPricing {
  if (planCode in PLAN_PRICING) {
    return PLAN_PRICING[planCode as PlanCode];
  }
  return PLAN_PRICING.COMMUNITY;
}

/**
 * Get metadata for a plan code.
 * Returns COMMUNITY metadata if plan code is invalid.
 */
export function getPlanMetadata(planCode: string): PlanMetadata {
  if (planCode in PLAN_METADATA) {
    return PLAN_METADATA[planCode as PlanCode];
  }
  return PLAN_METADATA.COMMUNITY;
}

/**
 * Get the price in cents for a plan and billing period.
 */
export function getDisplayPrice(planCode: PlanCode, period: BillingPeriod): number {
  const pricing = PLAN_PRICING[planCode];
  return period === 'annual' ? pricing.annualPriceCents : pricing.monthlyPriceCents;
}

/**
 * Get all paid plan codes.
 */
export function getPaidPlans(): PlanCode[] {
  return PLAN_ORDER.filter((code) => PLAN_METADATA[code].paid);
}
