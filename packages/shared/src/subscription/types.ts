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
  /** Self-service delegation cert issuance from the customer portal */
  delegationCerts: boolean;
}

/**
 * Subscription data payload.
 * This is the data that gets signed by the account server.
 */
export interface SubscriptionData {
  /** Schema version (2 = chain-enabled) */
  version: 2;
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

  // Chain (tamper-evident issuance ledger)
  /** Global monotonic sequence number per subscription */
  sequence: number;
  /** Hash of the previous issuance ledger entry ("genesis" for first) */
  prevChainHash: string;

  // Attribution
  /** Email of the account holder who issued this license */
  issuedByEmail?: string;
  /** Company/organization name */
  companyName?: string;
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
  /** Chain hash: SHA256(prevChainHash + ":" + payload). Computed post-signing. */
  chainHash?: string;
}

export type RepoLicenseKind = 'grand' | 'fork';

export interface RepoLicense {
  version: 2;
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
  /**
   * Identity of the datastore the repo lives in. Validated by renet exactly
   * like luksUuid/storageFingerprint, so a same-node fork (which mints its own
   * datastore identity) fails closed and re-meters on first touch.
   */
  datastoreId?: string;
  /**
   * Absolute URL of the issuing server's `POST /licenses/renew` endpoint. The
   * server self-describes so renet — which holds no account credentials and
   * knows no server address — can renew using the blob itself as the bearer.
   * Absent on blobs issued before self-renewal existed.
   */
  renewalUrl?: string;
  issuedAt: string;
  refreshRecommendedAt: string;
  hardExpiresAt: string;
  /** Global monotonic sequence number per subscription */
  sequence: number;
  /** Hash of the previous issuance ledger entry */
  prevChainHash: string;
  issuedByEmail?: string;
  companyName?: string;
}

export interface SignedRepoLicense {
  payload: string;
  signature: string;
  publicKeyId: string;
  /** Chain hash: SHA256(prevChainHash + ":" + payload). Computed post-signing. */
  chainHash?: string;
  /**
   * Delegation certificate embedded in on-premise-signed licenses. Present
   * when the license was signed by a delegated key rather than the upstream
   * master key; renet validates it against its baked master key before
   * trusting the delegated signature.
   */
  delegationCert?: SignedDelegationCert;
}

/**
 * Signed delegation certificate.
 * Wraps a {@link DelegationCert} payload with the upstream master key's
 * Ed25519 signature. Travels embedded in on-premise-signed repo licenses.
 */
export interface SignedDelegationCert {
  /** Base64-encoded DelegationCert JSON */
  payload: string;
  /** Base64-encoded Ed25519 signature by the upstream master key */
  signature: string;
  /** Fingerprint of the upstream master key that signed this cert */
  publicKeyId: string;
}

/**
 * Delegation certificate for on-premise license signing.
 * Signed by the upstream master key. Authorizes a delegated key to sign
 * licenses within the specified constraints.
 */
export interface DelegationCert {
  version: 1;
  subscriptionId: string;
  planCode: PlanCode;
  maxMachines: number;
  maxRepositorySizeGb: number;
  maxRepoLicenseIssuancesPerMonth: number;
  /**
   * Backup-storage quota in PHYSICAL unique stored bytes for this subscription.
   * Rides inside the signed cert (populated from the subscription row, like
   * maxRepositorySizeGb) because the on-prem admin has no subscription-edit
   * surface. Optional for backward compatibility — certs issued before storage
   * backups default to the plan value when read.
   */
  storageQuotaBytes?: number;
  /** Upper bound on the chain sequence number */
  maxTotalIssuances: number;
  /** Base64 SPKI Ed25519 public key of the on-premise server */
  delegatedPublicKey: string;
  /** Chain starting point (continuation from previous cert or "genesis") */
  genesisHash: string;
  /**
   * Chain sequence at which this cert was issued. Used by on-premise upload
   * verification to validate that the new cert's chain anchor still links to
   * an entry in the local issuance ledger (sequence-advancement during
   * air-gapped renewal transit). Optional for backward compatibility — older
   * certs default to 0 when read.
   */
  genesisSequence?: number;
  validFrom: string;
  validUntil: string;
  issuedAt: string;
}

/**
 * API token scopes for machine licensing.
 */
export type ApiTokenScope =
  | 'license:read'
  | 'license:activate'
  | 'subscription:read'
  | 'audit:write'
  | 'delegation:renew'
  // Proxy plane (rdc serve): `proxy:exec` lets a client submit commands to an
  // executor, `proxy:admin` lets it manage the executor itself. `proxy:admin` is
  // privileged (owner/admin only); `proxy:exec` is creatable by any member.
  | 'proxy:exec'
  | 'proxy:admin'
  // Config plane: `config:enroll` lets a headless CLI add a password key slot to
  // its own config-store membership (rdc config remote enable --password).
  // Creatable by any member — not privileged.
  | 'config:enroll'
  // Backup plane: `backup:read` lets a CLI query the subscription's backup
  // storage state through the tunnel (usage, manifest index, verify). Read-only,
  // creatable by any member — not privileged. The MACHINE never holds this: it
  // commits its own manifests via the license-blob storage session.
  | 'backup:read'
  // `backup:manage` declares the server-enforced GFS retention policy, which
  // SCHEDULES DELETIONS. It is deliberately not folded into `backup:read`: a
  // token minted to show a usage bar must not be able to shrink history.
  | 'backup:manage';

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
  createdByUserId?: string | null;
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
  /** Purchasable via self-serve checkout. False = fallback-only (COMMUNITY) or partner-only (ENTERPRISE). */
  selfServe: boolean;
  /**
   * The web console (browser-driven command execution through an executor) is
   * available on this plan. Off for COMMUNITY: the console runs real commands
   * against real machines on the operator's behalf, which is a paid capability.
   */
  webConsole: boolean;
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
