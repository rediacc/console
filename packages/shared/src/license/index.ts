/**
 * @rediacc/shared/license
 *
 * Centralized license schema for the Rediacc platform.
 * Used by license-server, middleware, renet, and CLI.
 */

// Types
export type {
  FeatureFlags,
  LicenseData,
  LicenseStatus,
  LicenseValidationResult,
  OrganizationLicense,
  PlanCode,
  ResourceLimits,
  SignedLicenseBlob,
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
  LICENSE_CONFIG,
  PLAN_FEATURES,
  PLAN_ORDER,
  PLAN_RESOURCES,
  PROGRESSIVE_LIMIT_KEYS,
} from './constants';

// Validation
export {
  calculateGracePeriodEnd,
  decodeLicensePayload,
  encodeLicensePayload,
  getEffectivePlanCode,
  isGracePeriodExpired,
  isInGracePeriod,
  isLicenseActive,
  isLicenseExpired,
  validateLicense,
  validateLicenseData,
  validateOrganizationLicense,
  validateResourceLimits,
  validateSignedBlob,
} from './validation';

// Crypto (Ed25519 signature verification)
export {
  clearPublicKeys,
  createSignedLicense,
  generateKeyPair,
  getPublicKeyIds,
  hasPublicKey,
  importPrivateKey,
  importPublicKey,
  signLicensePayload,
  verifyAndDecodeLicense,
  verifySignature,
} from './crypto';
