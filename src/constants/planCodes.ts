/**
 * Plan Code Constants
 *
 * Centralized definition of subscription plan codes used throughout the system.
 * These constants ensure consistency between frontend, backend, and database.
 *
 * IMPORTANT: These values must match:
 * - Database plan codes in middleware/scripts/db_middleware_*.sql
 * - Pricing configuration in docs/static/data/pricing.json
 * - Tier configuration in docs/static/data/tiers.json
 */

export const PLAN_CODES = {
  COMMUNITY: 'COMMUNITY',
  PROFESSIONAL: 'PROFESSIONAL',
  BUSINESS: 'BUSINESS',
  ENTERPRISE: 'ENTERPRISE',
} as const;

export type PlanCode = typeof PLAN_CODES[keyof typeof PLAN_CODES];

/**
 * Plan code display names for UI
 */
export const PLAN_NAMES: Record<PlanCode, string> = {
  [PLAN_CODES.COMMUNITY]: 'Community',
  [PLAN_CODES.PROFESSIONAL]: 'Professional',
  [PLAN_CODES.BUSINESS]: 'Business',
  [PLAN_CODES.ENTERPRISE]: 'Enterprise',
};

/**
 * Plan code mapping for pricing configuration keys (lowercase)
 */
export const PLAN_PRICING_KEYS: Record<PlanCode, string> = {
  [PLAN_CODES.COMMUNITY]: 'community',
  [PLAN_CODES.PROFESSIONAL]: 'professional',
  [PLAN_CODES.BUSINESS]: 'business',
  [PLAN_CODES.ENTERPRISE]: 'enterprise',
};

/**
 * Plan tier order (for sorting and comparisons)
 */
export const PLAN_ORDER: Record<PlanCode, number> = {
  [PLAN_CODES.COMMUNITY]: 1,
  [PLAN_CODES.PROFESSIONAL]: 2,
  [PLAN_CODES.BUSINESS]: 3,
  [PLAN_CODES.ENTERPRISE]: 4,
};

/**
 * Check if a plan code is valid
 */
export const isValidPlanCode = (code: string): code is PlanCode => {
  return Object.values(PLAN_CODES).includes(code as PlanCode);
};

/**
 * Get plan tier level for comparison
 */
export const getPlanTier = (code: PlanCode): number => {
  return PLAN_ORDER[code];
};

/**
 * Check if plan A is higher tier than plan B
 */
export const isHigherTier = (planA: PlanCode, planB: PlanCode): boolean => {
  return getPlanTier(planA) > getPlanTier(planB);
};

/**
 * Check if plan A is at least the same tier as plan B
 */
export const isAtLeastTier = (planA: PlanCode, planB: PlanCode): boolean => {
  return getPlanTier(planA) >= getPlanTier(planB);
};

/**
 * Plans that have access to advanced features
 */
export const ADVANCED_FEATURE_PLANS: PlanCode[] = [
  PLAN_CODES.BUSINESS,
  PLAN_CODES.ENTERPRISE,
];

/**
 * Plans that have access to distributed storage features
 */
export const DISTRIBUTED_STORAGE_PLANS: PlanCode[] = [
  PLAN_CODES.BUSINESS,
  PLAN_CODES.ENTERPRISE,
];

/**
 * Plans that have priority support
 */
export const PRIORITY_SUPPORT_PLANS: PlanCode[] = [
  PLAN_CODES.PROFESSIONAL,
  PLAN_CODES.BUSINESS,
  PLAN_CODES.ENTERPRISE,
];

/**
 * Check if a plan has access to a specific feature set
 */
export const planHasFeature = (
  plan: PlanCode,
  feature: 'advanced' | 'distributedStorage' | 'prioritySupport' | 'dedicatedAccount'
): boolean => {
  switch (feature) {
    case 'advanced':
      return ADVANCED_FEATURE_PLANS.includes(plan);
    case 'distributedStorage':
      return DISTRIBUTED_STORAGE_PLANS.includes(plan);
    case 'prioritySupport':
      return PRIORITY_SUPPORT_PLANS.includes(plan);
    case 'dedicatedAccount':
      return plan === PLAN_CODES.ENTERPRISE;
    default:
      return false;
  }
};
