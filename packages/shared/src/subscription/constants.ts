/**
 * Subscription Constants
 *
 * Single source of truth for plan resources and features.
 * All components (account-server, renet, CLI) should use these values.
 */

import type {
  BillingPeriod,
  FeatureFlags,
  FloatingLicenceRange,
  PlanCaps,
  PlanCode,
  PlanMetadata,
  PlanPricing,
  PricingBasis,
} from './types.js';

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
    /**
     * Default backup-storage quota in PHYSICAL unique stored bytes (what R2
     * bills; dedup benefit passes to the user). Nullable per-subscription
     * override + usage-adjustment live on the subscription row; this is only the
     * plan default. Deliberately NOT edge-doubled (see the account server's
     * `getLimitsForEnvironment`): stored bytes are a real recurring bill, not a
     * marketing knob. On-prem transport rides the signed delegation cert.
     */
    storageQuotaBytes: number;
    /**
     * Forensic-capture quota in bytes (raw batches and day files together).
     * A quarter of `storageQuotaBytes` for the plans that ship forensics; FREE
     * and COMMUNITY ship none. A per-subscription override applies to
     * ENTERPRISE only.
     */
    forensicsQuotaBytes: number;
  }
> = {
  FREE: {
    maxRepositorySizeGb: 3,
    maxRepoLicenseIssuancesPerMonth: 0,
    storageQuotaBytes: 0,
    forensicsQuotaBytes: 0,
  },
  COMMUNITY: {
    maxRepositorySizeGb: 10,
    maxRepoLicenseIssuancesPerMonth: 100,
    storageQuotaBytes: 10 * 1024 ** 3,
    forensicsQuotaBytes: 0,
  },
  PROFESSIONAL: {
    maxRepositorySizeGb: 100,
    maxRepoLicenseIssuancesPerMonth: 2000,
    storageQuotaBytes: 100 * 1024 ** 3,
    forensicsQuotaBytes: 25 * 1024 ** 3,
  },
  BUSINESS: {
    maxRepositorySizeGb: 500,
    maxRepoLicenseIssuancesPerMonth: 5000,
    storageQuotaBytes: 500 * 1024 ** 3,
    forensicsQuotaBytes: 125 * 1024 ** 3,
  },
  ENTERPRISE: {
    maxRepositorySizeGb: 1024,
    maxRepoLicenseIssuancesPerMonth: 15000,
    storageQuotaBytes: 2048 * 1024 ** 3,
    forensicsQuotaBytes: 512 * 1024 ** 3,
  },
} as const;

/** Plan-default backup storage quota in bytes (COMMUNITY fallback). */
export function getStorageQuotaBytesForPlan(planCode: string): number {
  if (Object.hasOwn(PLAN_LIMITS, planCode)) {
    return PLAN_LIMITS[planCode as PlanCode].storageQuotaBytes;
  }
  return PLAN_LIMITS.COMMUNITY.storageQuotaBytes;
}

/** Plan-default forensic-capture quota in bytes (COMMUNITY fallback, which is 0). */
export function getForensicsQuotaBytesForPlan(planCode: string): number {
  if (Object.hasOwn(PLAN_LIMITS, planCode)) {
    return PLAN_LIMITS[planCode as PlanCode].forensicsQuotaBytes;
  }
  return PLAN_LIMITS.COMMUNITY.forensicsQuotaBytes;
}

/** The six GFS retention knobs, as a plan states them. */
export interface BackupRetentionKnobs {
  keepLast: number | null;
  keepHourly: number | null;
  keepDaily: number | null;
  keepWeekly: number | null;
  keepMonthly: number | null;
  keepYearly: number | null;
}

/**
 * Per-plan backup retention: the policy a lineage gets when no row is declared
 * (`default`), and the most a declared policy may ask for (`limit`).
 *
 * A limit of `null` leaves that knob uncapped (the storage quota still bounds
 * the bytes); `0` means the plan does not offer the knob, so any positive value
 * is refused. Kept beside PLAN_LIMITS rather than inside it because
 * PLAN_LIMITS is a flat number map that the generated subscription schema and
 * renet's schema test read as `map[string]map[string]int`.
 *
 * `allowKeepAll` says whether a declared policy with every knob unset (keep
 * every snapshot, bounded only by the storage quota) is offered. COMMUNITY
 * does not offer it.
 */
export const PLAN_BACKUP_RETENTION: Record<
  PlanCode,
  { default: BackupRetentionKnobs; limit: BackupRetentionKnobs; allowKeepAll: boolean }
> = {
  FREE: {
    default: {
      keepLast: 0,
      keepHourly: 0,
      keepDaily: 0,
      keepWeekly: 0,
      keepMonthly: 0,
      keepYearly: 0,
    },
    limit: {
      keepLast: 0,
      keepHourly: 0,
      keepDaily: 0,
      keepWeekly: 0,
      keepMonthly: 0,
      keepYearly: 0,
    },
    allowKeepAll: false,
  },
  COMMUNITY: {
    default: {
      keepLast: 3,
      keepHourly: null,
      keepDaily: 7,
      keepWeekly: null,
      keepMonthly: null,
      keepYearly: null,
    },
    limit: {
      keepLast: 3,
      keepHourly: 0,
      keepDaily: 7,
      keepWeekly: 0,
      keepMonthly: 0,
      keepYearly: 0,
    },
    allowKeepAll: false,
  },
  PROFESSIONAL: {
    default: {
      keepLast: 7,
      keepHourly: null,
      keepDaily: 7,
      keepWeekly: 4,
      keepMonthly: 6,
      keepYearly: null,
    },
    limit: {
      keepLast: null,
      keepHourly: null,
      keepDaily: 7,
      keepWeekly: 4,
      keepMonthly: 6,
      keepYearly: 0,
    },
    allowKeepAll: true,
  },
  BUSINESS: {
    default: {
      keepLast: 7,
      keepHourly: null,
      keepDaily: 14,
      keepWeekly: 8,
      keepMonthly: 12,
      keepYearly: 1,
    },
    limit: {
      keepLast: null,
      keepHourly: null,
      keepDaily: 14,
      keepWeekly: 8,
      keepMonthly: 12,
      keepYearly: 1,
    },
    allowKeepAll: true,
  },
  ENTERPRISE: {
    default: {
      keepLast: 7,
      keepHourly: null,
      keepDaily: 30,
      keepWeekly: 12,
      keepMonthly: 24,
      keepYearly: 7,
    },
    limit: {
      keepLast: null,
      keepHourly: null,
      keepDaily: 30,
      keepWeekly: 12,
      keepMonthly: 24,
      keepYearly: 7,
    },
    allowKeepAll: true,
  },
} as const;

/**
 * The keep-within window a plan offers (D-retention, decision O3): `defaultSeconds` is what a
 * strategy with a declared target gets when it names none (null where the plan has no cloud
 * backup), `limitSeconds` the most a declared policy may ask for (0 means the plan does not offer
 * the knob). A separate table from PLAN_BACKUP_RETENTION because that one counts snapshots and
 * this one counts time. COMMUNITY's limit forbids `keepHourly`, so allowing a window there is a
 * real change in what that plan can keep.
 */
export const PLAN_BACKUP_KEEP_WITHIN: Record<
  PlanCode,
  { defaultSeconds: number | null; limitSeconds: number }
> = {
  FREE: { defaultSeconds: null, limitSeconds: 0 },
  COMMUNITY: { defaultSeconds: 24 * 3600, limitSeconds: 24 * 3600 },
  PROFESSIONAL: { defaultSeconds: 24 * 3600, limitSeconds: 72 * 3600 },
  BUSINESS: { defaultSeconds: 48 * 3600, limitSeconds: 7 * 24 * 3600 },
  ENTERPRISE: { defaultSeconds: 72 * 3600, limitSeconds: 30 * 24 * 3600 },
} as const;

/**
 * The window above the plan's limit, or undefined when it fits. An unknown plan has no limit, like
 * every other retention knob (retentionAbovePlan in the account's backup-gc service).
 */
export function keepWithinAbovePlan(
  planCode: string | null | undefined,
  requestedSeconds: number
): { knob: 'keepWithinSeconds'; requested: number; limit: number } | undefined {
  if (!planCode || !Object.hasOwn(PLAN_BACKUP_KEEP_WITHIN, planCode)) return undefined;
  const limit = PLAN_BACKUP_KEEP_WITHIN[planCode as PlanCode].limitSeconds;
  return requestedSeconds > limit
    ? { knob: 'keepWithinSeconds', requested: requestedSeconds, limit }
    : undefined;
}

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
  FREE: {
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
 * Length of the self-serve free trial (Professional/Business checkout).
 * Card is collected up front; the first charge lands when the trial ends.
 */
export const TRIAL_PERIOD_DAYS = 14;

/**
 * All valid plan codes in order from lowest to highest tier.
 */
export const PLAN_ORDER: readonly PlanCode[] = [
  'FREE',
  'COMMUNITY',
  'PROFESSIONAL',
  'BUSINESS',
  'ENTERPRISE',
] as const;

/**
 * Maximum machines allowed per plan.
 *
 * Every self-serve plan includes exactly one Floating license (machine).
 * Multi-machine deployments are an Enterprise concern, sold through partners;
 * the ENTERPRISE value applies to partner-negotiated subscriptions only.
 */
export const PLAN_MAX_MACHINES: Record<PlanCode, number> = {
  FREE: 1,
  COMMUNITY: 1,
  PROFESSIONAL: 1,
  BUSINESS: 1,
  ENTERPRISE: 25,
} as const;

/**
 * Default delegation cert validity in days, by plan.
 * Used when neither the request nor a per-subscription override specifies a value.
 */
export const PLAN_DELEGATION_CERT_DEFAULT_DAYS: Record<PlanCode, number> = {
  FREE: 2,
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
  FREE: 2,
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
 * Mount prefix of the account API on an upstream origin. The portal hands out
 * UPSTREAM_URL as a bare origin, so the client appends the full path below.
 */
export const ACCOUNT_API_BASE_PATH = '/account/api/v1' as const;

/**
 * Full upstream API path (under the account API mount) for the delegation
 * cert renewal endpoint. Defined here
 * (rather than hard-coded inside the on-prem CertAutoRenewService) so the
 * upstream router and the on-prem auto-renew client agree on the same path.
 * The type system does not tie the two ends: the client imports this constant,
 * the router mounts its own literal, and a mismatch surfaces as a 404 at
 * runtime. `__tests__/constants-paths.test.ts` pins the value, so a change shows up in review.
 */
export const DELEGATION_RENEW_PATH = `${ACCOUNT_API_BASE_PATH}/delegation/renew` as const;

/**
 * API path (relative to the account server's base URL) of the repo-license
 * self-renewal endpoint. Stamped into every issued license as `renewalUrl` so
 * the machine renews against the server that issued the blob — cloud, edge, or
 * on-premise — without carrying any server configuration of its own.
 */
export const LICENSE_RENEW_PATH = '/account/api/v1/licenses/renew' as const;

/**
 * How long a repo license stays valid after its machineId stops matching.
 * Covers VM migrations that change the hardware fingerprint. Mirrored on the
 * Go side as `license.MachineIDGracePeriod` (renet
 * `pkg/license/types.go`); the two MUST agree, because the account server
 * applies this window when deciding whether to re-bind a renewed license to
 * the presented machine, and renet applies it when validating the result.
 */
export const MACHINE_ID_GRACE_PERIOD_DAYS = 40;
export const MACHINE_ID_GRACE_PERIOD_MS = MACHINE_ID_GRACE_PERIOD_DAYS * 24 * 60 * 60 * 1000;

/**
 * Get maximum machines for a plan code.
 * Returns COMMUNITY limit if plan code is invalid.
 */
export function getMaxMachines(planCode: string): number {
  if (Object.hasOwn(PLAN_MAX_MACHINES, planCode)) {
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
  'storageQuotaBytes',
  'forensicsQuotaBytes',
] as const;

/**
 * Get resources for a plan code.
 * Returns COMMUNITY resources if plan code is invalid.
 */
export function getPlanLimits(planCode: string): (typeof PLAN_LIMITS)[PlanCode] {
  if (Object.hasOwn(PLAN_LIMITS, planCode)) {
    return PLAN_LIMITS[planCode as PlanCode];
  }
  return PLAN_LIMITS.COMMUNITY;
}

/**
 * Get features for a plan code.
 * Returns COMMUNITY features if plan code is invalid.
 */
export function getPlanFeatures(planCode: string): FeatureFlags {
  if (Object.hasOwn(PLAN_FEATURES, planCode)) {
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
 * List price per floating licence per year, in whole USD, for the three paid editions (PLAN-pricing-plan-model.md R3). These are the partner catalog's edition rates: the catalog (private/account/src/pricing/catalog.default.ts) reads its `ratePerMachine` values from here, so the catalog, the account server and www price from one table.
 */
export const PLAN_EDITION_RATE_USD_PER_YEAR = {
  PROFESSIONAL: 550,
  BUSINESS: 700,
  ENTERPRISE: 900,
} as const satisfies Partial<Record<PlanCode, number>>;

/** Monthly billing costs 15% more than annual: monthly = annual x 1.15 / 12 (R3). */
export const MONTHLY_BILLING_MARKUP = 1.15;

/** Per-licence price from an edition rate (Design 2): annual = rate x 100 cents; monthly = round(rate x 1.15 / 12) whole dollars, in cents. */
function editionPricing(ratePerYearUsd: number): PlanPricing {
  return {
    monthlyPriceCents: Math.round((ratePerYearUsd * MONTHLY_BILLING_MARKUP) / 12) * 100,
    annualPriceCents: ratePerYearUsd * 100,
    currency: 'usd',
  };
}

/**
 * Pricing by plan, PER FLOATING LICENCE. Amounts in cents (USD). Derived from PLAN_EDITION_RATE_USD_PER_YEAR (Design 2), never typed by hand: Professional $550/yr or $53/mo, Business $700/yr or $67/mo, Enterprise $900/yr or $86/mo. ENTERPRISE is sold through partners only (never self-serve checkout).
 */
export const PLAN_PRICING: Record<PlanCode, PlanPricing> = {
  FREE: {
    monthlyPriceCents: 0,
    annualPriceCents: 0,
    currency: 'usd',
  },
  COMMUNITY: {
    monthlyPriceCents: 0,
    annualPriceCents: 0,
    currency: 'usd',
  },
  PROFESSIONAL: editionPricing(PLAN_EDITION_RATE_USD_PER_YEAR.PROFESSIONAL),
  BUSINESS: editionPricing(PLAN_EDITION_RATE_USD_PER_YEAR.BUSINESS),
  ENTERPRISE: editionPricing(PLAN_EDITION_RATE_USD_PER_YEAR.ENTERPRISE),
} as const;

// =============================================================================
// PLAN MODEL DIMENSIONS (PLAN-pricing-plan-model.md Design 1, rulings R4-R8)
// =============================================================================
//
// Kept beside PLAN_LIMITS rather than inside it, for the reason PLAN_BACKUP_RETENTION is: PLAN_LIMITS is the flat number map the generated subscription schema hands renet's schema test as `map[string]map[string]int`, which takes neither a null (unlimited) nor a string (pricing basis) nor a key renet does not know.

/**
 * User, repository and CPU caps by plan code, for the 'paid' pricing basis (R4, R5). FREE and COMMUNITY users are 1 (PLAN-pricing-seat-repo-caps.md R1). FREE repositories are 1, the one repository a Free License covers. COMMUNITY repositories have no ruling yet and stay uncapped, as they are today. ENTERPRISE repositories are per quote (the subscription override).
 */
export const PLAN_CAPS: Record<PlanCode, PlanCaps> = {
  FREE: { maxUsers: 1, maxRepositories: 1, maxCpusPerMachine: 16 },
  COMMUNITY: { maxUsers: 1, maxRepositories: null, maxCpusPerMachine: 16 },
  PROFESSIONAL: { maxUsers: 25, maxRepositories: 100, maxCpusPerMachine: 32 },
  BUSINESS: { maxUsers: null, maxRepositories: 250, maxCpusPerMachine: 64 },
  ENTERPRISE: { maxUsers: null, maxRepositories: null, maxCpusPerMachine: null },
} as const;

/** One plan's base: the PLAN_LIMITS row plus its PLAN_CAPS row. */
export type PlanBaseLimits = (typeof PLAN_LIMITS)[PlanCode] & PlanCaps;

/**
 * Free Professional: the PROFESSIONAL plan code on the 'free-eligible' basis. These values replace the PROFESSIONAL ones (R4: 16 CPUs; R5: 10 users, 25 repositories; R6: 500 setups a month, 25 GiB hosted R2). Every other dimension is the PROFESSIONAL one.
 */
export const FREE_PROFESSIONAL_LIMITS = {
  maxRepoLicenseIssuancesPerMonth: 500,
  storageQuotaBytes: 25 * 1024 ** 3,
  maxUsers: 10,
  maxRepositories: 25,
  maxCpusPerMachine: 16,
} as const satisfies Partial<PlanBaseLimits>;

/** The dimensions that multiply by the subscription's floating-licence count. */
export type PerLicenceDimension =
  | 'maxRepositories'
  | 'maxRepoLicenseIssuancesPerMonth'
  | 'storageQuotaBytes';

/**
 * Which dimensions scale per floating licence, by plan code on the 'paid' basis (R5, R6): Professional and Business repositories, setups and hosted R2 are per licence. Users never scale. Free Professional is one licence and scales nothing; ENTERPRISE is quoted through the per-subscription overrides.
 */
export const PLAN_PER_LICENCE_DIMENSIONS: Record<PlanCode, readonly PerLicenceDimension[]> = {
  FREE: [],
  COMMUNITY: [],
  PROFESSIONAL: ['maxRepositories', 'maxRepoLicenseIssuancesPerMonth', 'storageQuotaBytes'],
  BUSINESS: ['maxRepositories', 'maxRepoLicenseIssuancesPerMonth', 'storageQuotaBytes'],
  ENTERPRISE: [],
} as const;

/**
 * The base limits of a plan code on a pricing basis, before licence scaling, overrides and boosts (the account server's resolveEffectiveLimits applies those). An unknown plan code resolves to COMMUNITY, as every other getter here does; so does 'free-eligible' on any code but PROFESSIONAL, because that pairing does not exist and must not grant a paid plan's limits for free.
 */
export function getPlanBaseLimits(
  planCode: string,
  pricingBasis: PricingBasis = 'paid'
): PlanBaseLimits {
  const code: PlanCode = Object.hasOwn(PLAN_LIMITS, planCode)
    ? (planCode as PlanCode)
    : 'COMMUNITY';
  if (pricingBasis === 'free-eligible') {
    if (code !== 'PROFESSIONAL') return { ...PLAN_LIMITS.COMMUNITY, ...PLAN_CAPS.COMMUNITY };
    return { ...PLAN_LIMITS.PROFESSIONAL, ...PLAN_CAPS.PROFESSIONAL, ...FREE_PROFESSIONAL_LIMITS };
  }
  return { ...PLAN_LIMITS[code], ...PLAN_CAPS[code] };
}

/** The per-licence dimensions of a plan code on a pricing basis (none on 'free-eligible'). */
export function getPerLicenceDimensions(
  planCode: string,
  pricingBasis: PricingBasis = 'paid'
): readonly PerLicenceDimension[] {
  if (pricingBasis === 'free-eligible') return [];
  if (!Object.hasOwn(PLAN_PER_LICENCE_DIMENSIONS, planCode)) {
    return PLAN_PER_LICENCE_DIMENSIONS.COMMUNITY;
  }
  return PLAN_PER_LICENCE_DIMENSIONS[planCode as PlanCode];
}

/** The fewest floating licences an Enterprise subscription carries: the partner catalog's machine minimum (catalog.default.ts `enterpriseCapacity.machines.min`), R7. */
export const ENTERPRISE_MIN_FLOATING_LICENCES = 40;

/** Floating licences per subscription (R7): Professional 1-5 and Business 1-39 self-serve, Enterprise 40 and up. Business stops one short of the Enterprise minimum. */
export const PLAN_FLOATING_LICENCES: Record<
  'PROFESSIONAL' | 'BUSINESS' | 'ENTERPRISE',
  FloatingLicenceRange
> = {
  PROFESSIONAL: { min: 1, max: 5 },
  BUSINESS: { min: 1, max: ENTERPRISE_MIN_FLOATING_LICENCES - 1 },
  ENTERPRISE: { min: ENTERPRISE_MIN_FLOATING_LICENCES, max: null },
} as const;

/**
 * The large-machine add-on (R8): each pass adds 8 logical CPUs to one named machine's ceiling, at $50 a month or $200 a year; at most 4 passes on a machine and 3 machines with passes per subscription. Beyond that is Enterprise. PLAN-pricing-cpu-ceiling.md sells and enforces it.
 */
export const LARGE_MACHINE_PASS = {
  cpusPerPass: 8,
  monthlyPriceCents: 5_000,
  annualPriceCents: 20_000,
  currency: 'usd',
  maxPassesPerMachine: 4,
  maxMachinesWithPassesPerSubscription: 3,
} as const;

/**
 * Display metadata by plan.
 */
export const PLAN_METADATA: Record<PlanCode, PlanMetadata> = {
  FREE: {
    displayName: 'Free License',
    description: '48-hour renewable licence for one repository of up to 3 GB, no account needed',
    paid: false,
    featured: false,
    selfServe: false,
    webConsole: false,
    rediaccAiCredits: false,
  },
  COMMUNITY: {
    displayName: 'Community',
    description: 'Free fallback plan that keeps one machine running after a cancelled trial',
    paid: false,
    featured: false,
    selfServe: false,
    webConsole: false,
    rediaccAiCredits: false,
  },
  PROFESSIONAL: {
    displayName: 'Professional',
    description: 'For individuals and small projects that need one production machine',
    paid: true,
    featured: true,
    selfServe: false,
    webConsole: true,
    rediaccAiCredits: false,
  },
  BUSINESS: {
    displayName: 'Business',
    description: 'For teams that need larger repositories and advanced management',
    paid: true,
    featured: false,
    selfServe: false,
    webConsole: true,
    rediaccAiCredits: false,
  },
  ENTERPRISE: {
    displayName: 'Enterprise',
    description: 'Multi-machine deployments, sold through partners — contact us',
    paid: true,
    featured: false,
    selfServe: false,
    webConsole: true,
    rediaccAiCredits: true,
  },
} as const;

/**
 * Get pricing for a plan code.
 * Returns COMMUNITY pricing if plan code is invalid.
 */
export function getPlanPricing(planCode: string): PlanPricing {
  if (Object.hasOwn(PLAN_PRICING, planCode)) {
    return PLAN_PRICING[planCode as PlanCode];
  }
  return PLAN_PRICING.COMMUNITY;
}

/**
 * Get metadata for a plan code.
 * Returns COMMUNITY metadata if plan code is invalid.
 */
export function getPlanMetadata(planCode: string): PlanMetadata {
  if (Object.hasOwn(PLAN_METADATA, planCode)) {
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
