/**
 * @rediacc/shared/subscription
 *
 * Centralized subscription schema for the Rediacc platform.
 * Used by account-server, middleware, renet, and CLI.
 */

// Constants
export {
  comparePlans,
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
  isValidPlanCode,
  DELEGATION_CERT_CREATE_RATE_LIMIT,
  DELEGATION_RENEW_PATH,
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
} from './constants';
// Air-gapped renewal manifest
export {
  canonicalManifestBytes,
  isManifestExpired,
  RENEWAL_MANIFEST_SCHEMA_VERSION,
  verifyManifestSignature,
} from './renewal-manifest';
export type {
  RenewalRequestManifest,
  SignedRenewalRequestManifest,
} from './renewal-manifest';
// Delegation cert validity policy
export {
  computeDelegationCertValidity,
  computeRenewalThresholdDays,
} from './delegation-cert-policy';
export type {
  ComputedValidity,
  ComputeValidityInput,
  ValidityClampReason,
} from './delegation-cert-policy';
// Signing keys (Ed25519 public keys for signature verification)
export { CURRENT_SIGNING_KEY, SIGNING_KEYS } from './signing-keys';
export type { SigningKey } from './signing-keys';
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
