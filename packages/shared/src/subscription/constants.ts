/**
 * Subscription Constants
 *
 * Single source of truth for plan resources and features.
 * All components (account-server, middleware, renet, CLI) should use these values.
 */

import type { BillingPeriod, FeatureFlags, PlanCode, PlanMetadata, PlanPricing } from './types';

/**
 * Resource limits by plan.
 * This is the canonical source of truth for all plan limits.
 *
 * `maxRepoLicenseIssuancesPerMonth` is a per-machine setup cap: each repo
 * license issuance licenses exactly one machine (1 issuance = 1 Floating
 * license). Paid-tier display copy renders these with a "+" suffix (e.g.
 * "2,000+") to signal room to grow / contact for more.
 */
export const PLAN_LIMITS: Record<
  PlanCode,
  {
    maxRepositorySizeGb: number;
    maxRepoLicenseIssuancesPerMonth: number;
  }
> = {
  COMMUNITY: {
    maxRepositorySizeGb: 10,
    maxRepoLicenseIssuancesPerMonth: 100,
  },
  PROFESSIONAL: {
    maxRepositorySizeGb: 50,
    maxRepoLicenseIssuancesPerMonth: 2000,
  },
  BUSINESS: {
    maxRepositorySizeGb: 200,
    maxRepoLicenseIssuancesPerMonth: 5000,
  },
  ENTERPRISE: {
    maxRepositorySizeGb: 1024,
    maxRepoLicenseIssuancesPerMonth: 15000,
  },
} as const;

/**
 * How long a machine holds its Floating license slot after the last repo
 * license issuance on that machine, before it auto-releases from inactivity.
 * Single source of truth for both the account server's enforcement
 * (`private/account/src/constants.ts` re-exports this) and any marketing/docs
 * copy referencing the auto-release window.
 */
export const MACHINE_AUTO_RELEASE_MS = 5 * 60 * 60 * 1000; // 5 hours
export const MACHINE_AUTO_RELEASE_HOURS = MACHINE_AUTO_RELEASE_MS / (60 * 60 * 1000);

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
    delegationCerts: false,
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
    delegationCerts: true,
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
    delegationCerts: true,
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
    delegationCerts: true,
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
  PROFESSIONAL: 3,
  BUSINESS: 10,
  ENTERPRISE: 25,
} as const;

/**
 * Default delegation cert validity in days, by plan.
 * Used when neither the request nor a per-subscription override specifies a value.
 */
export const PLAN_DELEGATION_CERT_DEFAULT_DAYS: Record<PlanCode, number> = {
  COMMUNITY: 15,
  PROFESSIONAL: 60,
  BUSINESS: 90,
  ENTERPRISE: 120,
} as const;

/**
 * Hard ceiling for delegation cert validity per plan.
 * Bypassed when a subscription has an explicit `delegationCertDefaultDays` override.
 */
export const PLAN_DELEGATION_CERT_MAX_DAYS: Record<PlanCode, number> = {
  COMMUNITY: 30,
  PROFESSIONAL: 120,
  BUSINESS: 180,
  ENTERPRISE: 365,
} as const;

/**
 * Maximum simultaneously-active delegation certs per subscription. Hard cap = 1.
 *
 * Each on-premise install enforces `maxRepoLicenseIssuancesPerMonth`,
 * `maxActivations`, and chain integrity against its OWN local issuance ledger.
 * If a subscription has multiple active certs (one per install), each install
 * enforces independently — multiplying the effective quota by the number of
 * installs with no possible upstream reconciliation.
 *
 * Single-active is the only enforceable model. Customers needing multiple
 * installs (production + staging + DR) must purchase one subscription per
 * install.
 */
export const MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION = 1;

/**
 * Maximum delegation cert create attempts per subscription per rolling window.
 *
 * Even with single-active enforcement, the loop revoke→create→revoke→create
 * burns one master-key signature per iteration. This rate limit caps the
 * signing-pipeline abuse rate even when the active count never exceeds 1.
 * Counts every attempt, including ones rejected by single-active (so a
 * collision-spam loop is also throttled).
 */
export const DELEGATION_CERT_CREATE_RATE_LIMIT = {
  maxAttempts: 10,
  windowMs: 24 * 60 * 60 * 1000,
} as const;

/**
 * Maximum age of an air-gapped renewal manifest before it is rejected as stale.
 * 7 days is generous for international physical-media shipping while limiting
 * replay surface.
 */
export const RENEWAL_MANIFEST_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

/**
 * Upstream API path for the delegation cert renewal endpoint. Defined here
 * (rather than hard-coded inside the on-prem CertAutoRenewService) so the
 * upstream router and the on-prem auto-renew client agree on the same path.
 * Both ends import this constant; changing one without the other is a
 * compile-time error in the consumer that uses it.
 */
export const DELEGATION_RENEW_PATH = '/api/v1/delegation/renew' as const;

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
export const PROGRESSIVE_LIMIT_KEYS: readonly (keyof (typeof PLAN_LIMITS)[PlanCode])[] = [
  'maxRepositorySizeGb',
  'maxRepoLicenseIssuancesPerMonth',
] as const;

/**
 * Get resources for a plan code.
 * Returns COMMUNITY resources if plan code is invalid.
 */
export function getPlanLimits(planCode: string): (typeof PLAN_LIMITS)[PlanCode] {
  if (planCode in PLAN_LIMITS) {
    return PLAN_LIMITS[planCode as PlanCode];
  }
  return PLAN_LIMITS.COMMUNITY;
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
export function getPlanLimit(
  planCode: string,
  limit: keyof (typeof PLAN_LIMITS)[PlanCode]
): number {
  const limits = getPlanLimits(planCode);
  return limits[limit];
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
    monthlyPriceCents: 7_900,
    annualPriceCents: 79_000,
    currency: 'usd',
  },
  BUSINESS: {
    monthlyPriceCents: 29_900,
    annualPriceCents: 299_000,
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
    description: 'Contact us for custom terms, limits, and dedicated support',
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
