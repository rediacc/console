/**
 * @rediacc/shared/subscription
 *
 * Centralized subscription schema for the Rediacc platform.
 * Used by account-server, middleware, renet, and CLI.
 */

// Constants
export {
  COMMUNITY_LEGACY_CUTOFF_ISO,
  comparePlans,
  DELEGATION_CERT_CREATE_RATE_LIMIT,
  DELEGATION_RENEW_PATH,
  exceedsLimit,
  getDisplayPrice,
  getMaxMachines,
  getPaidPlans,
  getPlanFeatures,
  getPlanLimit,
  getPlanLimits,
  getPlanMetadata,
  getPlanPricing,
  getStripeLookupKey,
  hasFeature,
  isCommunityUsable,
  isValidPlanCode,
  MACHINE_AUTO_RELEASE_HOURS,
  MACHINE_AUTO_RELEASE_MS,
  MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION,
  PLAN_DELEGATION_CERT_DEFAULT_DAYS,
  PLAN_DELEGATION_CERT_MAX_DAYS,
  PLAN_FEATURES,
  PLAN_LIMITS,
  PLAN_MAX_MACHINES,
  PLAN_METADATA,
  PLAN_ORDER,
  PLAN_PRICING,
  PROGRESSIVE_LIMIT_KEYS,
  RENEWAL_MANIFEST_MAX_AGE_MS,
  SUBSCRIPTION_CONFIG,
  TRIAL_PERIOD_DAYS,
} from './constants';
// Crypto (Ed25519 signature verification)
export {
  clearPublicKeys,
  computeChainHash,
  createSignedSubscription,
  generateKeyPair,
  getPublicKeyIds,
  hasPublicKey,
  importPrivateKey,
  importPublicKey,
  signSubscriptionPayload,
  verifyAndDecodeSubscription,
  verifySignature,
} from './crypto';
export type {
  ComputedValidity,
  ComputeValidityInput,
  ValidityClampReason,
} from './delegation-cert-policy';
// Delegation cert validity policy
export {
  computeDelegationCertValidity,
  computeRenewalThresholdDays,
  SubscriptionExpiredForDelegationError,
} from './delegation-cert-policy';
// Public-key fingerprint (shared with Go renet)
export {
  computePublicKeyId,
  isValidPublicKeyId,
  PUBLIC_KEY_ID_PATTERN,
} from './fingerprint';
export type {
  RenewalRequestManifest,
  SignedRenewalRequestManifest,
} from './renewal-manifest';
// Air-gapped renewal manifest
export {
  canonicalManifestBytes,
  isManifestExpired,
  RENEWAL_MANIFEST_SCHEMA_VERSION,
  verifyManifestSignature,
} from './renewal-manifest';
export type { SigningKey } from './signing-keys';
// Signing keys (Ed25519 public keys for signature verification)
export { CURRENT_SIGNING_KEY, SIGNING_KEYS } from './signing-keys';
// Types
export type {
  ApiToken,
  ApiTokenScope,
  BillingPeriod,
  DelegationCert,
  FeatureFlags,
  OrganizationSubscription,
  PlanCode,
  PlanMetadata,
  PlanPricing,
  RepoLicense,
  RepoLicenseKind,
  SignedDelegationCert,
  SignedRepoLicense,
  SignedSubscriptionBlob,
  SubscriptionData,
  SubscriptionStatus,
  SubscriptionValidationResult,
} from './types';
// Validation
export {
  calculateGracePeriodEnd,
  decodeSubscriptionPayload,
  encodeSubscriptionPayload,
  getEffectivePlanCode,
  isGracePeriodExpired,
  isInGracePeriod,
  isSubscriptionActive,
  isSubscriptionExpired,
  validateOrganizationSubscription,
  validateSignedBlob,
  validateSubscription,
  validateSubscriptionData,
} from './validation';
