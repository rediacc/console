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
  PLAN_FEATURES,
  PLAN_LIMITS,
  PLAN_MAX_MACHINES,
  PLAN_METADATA,
  PLAN_ORDER,
  PLAN_PRICING,
  PROGRESSIVE_LIMIT_KEYS,
  SUBSCRIPTION_CONFIG,
} from './constants';
// Crypto (Ed25519 signature verification)
export {
  clearPublicKeys,
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
