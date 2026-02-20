/**
 * @rediacc/shared/subscription
 *
 * Centralized subscription schema for the Rediacc platform.
 * Used by account-server, middleware, renet, and CLI.
 */

// Types
export type {
  FeatureFlags,
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
  getResourceLimit,
  getPlanFeatures,
  getPlanResources,
  hasFeature,
  isValidPlanCode,
  SUBSCRIPTION_CONFIG,
  PLAN_FEATURES,
  PLAN_ORDER,
  PLAN_RESOURCES,
  PROGRESSIVE_LIMIT_KEYS,
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
