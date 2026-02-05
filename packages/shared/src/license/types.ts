/**
 * License Types
 *
 * Centralized type definitions for the licensing system.
 * Used by license-server, middleware, renet, and CLI.
 */

/**
 * Subscription plan codes.
 */
export type PlanCode = 'COMMUNITY' | 'PROFESSIONAL' | 'BUSINESS' | 'ENTERPRISE';

/**
 * License status values.
 */
export type LicenseStatus = 'ACTIVE' | 'INACTIVE' | 'EXPIRED' | 'SUSPENDED' | 'GRACE';

/**
 * Resource limits per subscription plan.
 * A value of -1 indicates unlimited.
 * A value of 0 indicates none/blocked.
 */
export interface ResourceLimits {
  /** Number of customer-created bridges allowed. 0 = none, -1 = unlimited */
  bridges: number;
  /** Maximum concurrent active jobs */
  maxActiveJobs: number;
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
 * License data payload.
 * This is the data that gets signed by the license server.
 */
export interface LicenseData {
  /** Schema version for migrations */
  version: 1;
  /** UUID from license server */
  licenseId: string;
  /** Middleware organization ID */
  organizationId: number;
  /** Customer identifier */
  customerId: string;
  /** Subscription plan code */
  planCode: PlanCode;
  /** Current license status */
  status: LicenseStatus;

  // Dates (ISO8601 format)
  /** When the license was issued */
  issuedAt: string;
  /** When the license expires */
  expiresAt: string;
  /** Last successful check-in with license server */
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
 * Signed license blob.
 * Contains the license payload and Ed25519 signature.
 */
export interface SignedLicenseBlob {
  /** Base64 encoded LicenseData JSON */
  payload: string;
  /** Base64 encoded Ed25519 signature */
  signature: string;
  /** Public key identifier for key rotation support */
  publicKeyId: string;
}

/**
 * License storage format in Organization.License column.
 */
export interface OrganizationLicense {
  /** The signed license blob from license server */
  signedBlob: SignedLicenseBlob;
  /** Cached decoded data for quick access (redundant but performant) */
  cachedData: {
    planCode: PlanCode;
    status: LicenseStatus;
    resources: ResourceLimits;
    features: FeatureFlags;
    expiresAt: string;
    gracePeriodEnds: string;
  };
}

/**
 * License validation result.
 */
export interface LicenseValidationResult {
  /** Whether the license is valid */
  valid: boolean;
  /** Decoded license data if valid */
  data?: LicenseData;
  /** Error message if invalid */
  error?: string;
  /** Whether the license is in grace period */
  inGracePeriod?: boolean;
}
