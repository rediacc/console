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
 * Resource limits per subscription plan.
 * A value of -1 indicates unlimited.
 * A value of 0 indicates none/blocked.
 */
export interface ResourceLimits {
  /** Number of customer-created bridges allowed. 0 = none, -1 = unlimited */
  bridges: number;
  /** Reserved job slots */
  maxReservedJobs: number;
  /** Maximum job timeout in hours */
  jobTimeoutHours: number;
  /** Maximum repository size in GB */
  maxRepositorySizeGb: number;
  /** Maximum jobs per month */
  maxJobsPerMonth: number;
  /** Maximum pending queue items per user */
  maxPendingPerUser: number;
  /** Maximum concurrent tasks per machine */
  maxTasksPerMachine: number;
  /** Ceph pools per team. 0 = none, -1 = unlimited */
  cephPoolsPerTeam: number;
}

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
  /** Resource limits for this plan */
  resources: ResourceLimits;
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

/**
 * Machine license payload.
 * Short-lived (1 hour), machine-specific, signed by account server.
 */
export interface MachineLicense {
  version: 1;
  subscriptionId: string;
  machineId: string;
  planCode: PlanCode;
  status: SubscriptionStatus;
  resources: ResourceLimits;
  features: FeatureFlags;
  issuedAt: string;
  expiresAt: string;
  sequenceNumber: number;
  ipAddress: string;
}

/**
 * Signed machine license blob (Ed25519).
 */
export interface SignedMachineLicense {
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
    resources: ResourceLimits;
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
