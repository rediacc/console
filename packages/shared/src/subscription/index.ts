/**
 * @rediacc/shared/subscription
 *
 * Centralized subscription schema for the Rediacc platform.
 * Used by account-server, middleware, renet, and CLI.
 */

// Types
export type {
  ApiToken,
  ApiTokenScope,
  BillingPeriod,
  FeatureFlags,
  MachineLicense,
  PlanMetadata,
  PlanPricing,
  SignedMachineLicense,
  SubscriptionData,
  SubscriptionStatus,
  SubscriptionValidationResult,
  OrganizationSubscription,
  PlanCode,
  ResourceLimits,
  SignedSubscriptionBlob,
} from './types';

// Constants
export {
  comparePlans,
  exceedsLimit,
  getDisplayPrice,
  getMaxMachines,
  getPaidPlans,
  getPlanFeatures,
  getPlanMetadata,
  getPlanPricing,
  getPlanResources,
  getResourceLimit,
  getStripeLookupKey,
  hasFeature,
  isValidPlanCode,
  PLAN_FEATURES,
  PLAN_MAX_MACHINES,
  PLAN_METADATA,
  PLAN_ORDER,
  PLAN_PRICING,
  PLAN_RESOURCES,
  PROGRESSIVE_LIMIT_KEYS,
  SUBSCRIPTION_CONFIG,
} from './constants';

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
  validateSubscription,
  validateSubscriptionData,
  validateOrganizationSubscription,
  validateResourceLimits,
  validateSignedBlob,
} from './validation';

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
