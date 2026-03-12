/**
 * Subscription Types
 *
 * Centralized type definitions for the subscription system.
 * Used by account-server, middleware, renet, and CLI.
 */

/**
 * Subscription plan codes.
 */
export type PlanCode = 'COMMUNITY' | 'PROFESSIONAL' | 'BUSINESS' | 'ENTERPRISE';

/**
 * Subscription status values.
 */
export type SubscriptionStatus = 'ACTIVE' | 'INACTIVE' | 'EXPIRED' | 'SUSPENDED' | 'GRACE';

/**
 * Feature availability flags per subscription plan.
 */
export interface FeatureFlags {
  /** Custom permission groups */
  permissionGroups: boolean;
  /** Ceph distributed storage */
  ceph: boolean;
  /** Queue priority management */
  queuePriority: boolean;
  /** Advanced analytics dashboard */
  advancedAnalytics: boolean;
  /** Priority support access */
  prioritySupport: boolean;
  /** Audit logging */
  auditLog: boolean;
  /** Advanced queue features */
  advancedQueue: boolean;
  /** Custom branding (remove "Powered by") */
  customBranding: boolean;
  /** Dedicated account manager */
  dedicatedAccount: boolean;
}

/**
 * Subscription data payload.
 * This is the data that gets signed by the account server.
 */
export interface SubscriptionData {
  /** Schema version for migrations */
  version: 1;
  /** UUID from account server */
  subscriptionId: string;
  /** Middleware organization ID */
  organizationId: number;
  /** Customer identifier */
  customerId: string;
  /** Subscription plan code */
  planCode: PlanCode;
  /** Current subscription status */
  status: SubscriptionStatus;

  // Dates (ISO8601 format)
  /** When the subscription was issued */
  issuedAt: string;
  /** When the subscription expires */
  expiresAt: string;
  /** Last successful check-in with account server */
  lastCheckIn: string;
  /** When grace period ends (3 days after lastCheckIn) */
  gracePeriodEnds: string;

  // Limits & Features
  /** Maximum repository size in GB */
  maxRepositorySizeGb: number;
  /** Maximum successful repo-license issuances per UTC calendar month */
  maxRepoLicenseIssuancesPerMonth: number;
  /** Feature flags for this plan */
  features: FeatureFlags;

  // Activation
  /** Maximum number of machine activations */
  maxActivations: number;
  /** Current activation count */
  activationCount: number;
}

/**
 * Signed subscription blob.
 * Contains the subscription payload and Ed25519 signature.
 */
export interface SignedSubscriptionBlob {
  /** Base64 encoded SubscriptionData JSON */
  payload: string;
  /** Base64 encoded Ed25519 signature */
  signature: string;
  /** Public key identifier for key rotation support */
  publicKeyId: string;
}

export type RepoLicenseKind = 'grand' | 'fork';

export interface RepoLicense {
  version: 1;
  subscriptionId: string;
  machineId: string;
  clientMachineId: string;
  repositoryGuid: string;
  grandGuid: string;
  kind: RepoLicenseKind;
  planCode: PlanCode;
  status: SubscriptionStatus;
  maxRepositorySizeGb: number;
  luksUuid?: string;
  storageFingerprint?: string;
  issuedAt: string;
  refreshRecommendedAt: string;
  hardExpiresAt: string;
}

export interface SignedRepoLicense {
  payload: string;
  signature: string;
  publicKeyId: string;
}

/**
 * API token scopes for machine licensing.
 */
export type ApiTokenScope = 'license:read' | 'license:activate' | 'subscription:read';

/**
 * API token for machine authentication.
 * Generated from web portal, IP-bound on first use.
 */
export interface ApiToken {
  id: string;
  name: string;
  tokenHash: string;
  subscriptionId: string;
  teamId: string | null;
  scopes: ApiTokenScope[];
  boundIp: string | null;
  createdAt: string;
  expiresAt: string | null;
  lastUsedAt: string | null;
  revokedAt: string | null;
}

/**
 * Subscription storage format in Organization.License column.
 */
export interface OrganizationSubscription {
  /** The signed subscription blob from account server */
  signedBlob: SignedSubscriptionBlob;
  /** Cached decoded data for quick access (redundant but performant) */
  cachedData: {
    planCode: PlanCode;
    status: SubscriptionStatus;
    maxRepositorySizeGb: number;
    maxRepoLicenseIssuancesPerMonth: number;
    features: FeatureFlags;
    expiresAt: string;
    gracePeriodEnds: string;
  };
}

/**
 * Billing period for Stripe subscriptions.
 */
export type BillingPeriod = 'monthly' | 'annual';

/**
 * Pricing configuration for a subscription plan.
 * Amounts are in cents (USD).
 */
export interface PlanPricing {
  monthlyPriceCents: number;
  annualPriceCents: number;
  currency: 'usd';
}

/**
 * Display metadata for a subscription plan.
 */
export interface PlanMetadata {
  displayName: string;
  description: string;
  paid: boolean;
  featured: boolean;
}

/**
 * Subscription validation result.
 */
export interface SubscriptionValidationResult {
  /** Whether the subscription is valid */
  valid: boolean;
  /** Decoded subscription data if valid */
  data?: SubscriptionData;
  /** Error message if invalid */
  error?: string;
  /** Whether the subscription is in grace period */
  inGracePeriod?: boolean;
}
