import { expect } from 'vitest';
import { type CliResult, getErrorMessage } from './cli.js';

/**
 * Assert that a CLI result represents an error with expected message content
 */
export function expectError(
  result: CliResult,
  expected: { messageContains: string; code?: string }
): void {
  expect(result.success, `Expected failure but got success. stdout: ${result.stdout}`).toBe(false);

  const errorMsg = getErrorMessage(result);

  if (expected.code) {
    expect(errorMsg).toContain(`[${expected.code}]`);
  }

  expect(errorMsg.toLowerCase()).toContain(expected.messageContains.toLowerCase());
}

/**
 * Generate a non-existent resource name for testing not-found scenarios
 */
export function nonExistentName(prefix: string): string {
  return `${prefix}-nonexistent-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

/**
 * Middleware error patterns from stored procedures.
 * These patterns match the RAISERROR messages in db_middleware_*.sql files.
 */
export const ErrorPatterns = {
  // Team errors (from db_middleware_organization.sql)
  TEAM_NOT_FOUND: 'not found in your organization',
  TEAM_ALREADY_EXISTS: 'already exists in your organization',
  TEAM_NOT_MEMBER: 'not a member of team',
  TEAM_CANNOT_DELETE_DEFAULT: 'Cannot delete the default',
  TEAM_CANNOT_DELETE_LAST: 'Cannot remove the last team',
  TEAM_CANNOT_RENAME_DEFAULT: 'Cannot rename the default',
  TEAM_NAME_EMPTY: 'cannot be empty',
  TEAM_VAULT_EMPTY: 'vault data cannot be null or empty',

  // Team membership errors
  USER_NOT_FOUND_IN_ORGANIZATION: 'not found, not activated, or not in your organization',
  USER_ALREADY_MEMBER: 'already a member of team',
  CANNOT_REMOVE_SELF: 'cannot remove yourself',
  BRIDGE_USER_CANNOT_JOIN: 'Bridge users cannot be added to teams',

  // Machine errors (from db_middleware_infrastructure.sql)
  MACHINE_NOT_FOUND: 'not found in team',
  MACHINE_ALREADY_EXISTS: 'already exists in your organization',
  MACHINE_BRIDGE_MISMATCH: 'not assigned to bridge',

  // Bridge errors
  BRIDGE_NOT_FOUND: 'not found in region',
  BRIDGE_ALREADY_EXISTS: 'already exists in region',
  BRIDGE_CANNOT_DELETE_DEFAULT: 'Cannot delete the default',

  // ========================================
  // INFRASTRUCTURE ERRORS (from db_middleware_infrastructure.sql)
  // ========================================

  // Resource limits
  BRIDGE_LIMIT_EXCEEDED: 'Resource limit exceeded for customer bridges',
  MACHINE_LIMIT_EXCEEDED: 'Resource limit exceeded for machines',

  // Vault validation
  BRIDGE_VAULT_EMPTY: 'Bridge vault data cannot be null or empty',
  MACHINE_VAULT_EMPTY: 'Machine vault data cannot be null or empty',
  REGION_VAULT_EMPTY: 'Region vault data cannot be null or empty',
  MACHINE_STATUS_EMPTY: 'Machine status data cannot be null or empty',

  // Name validation
  BRIDGE_NAME_EMPTY: 'New bridge name cannot be empty',
  MACHINE_NAME_EMPTY: 'New machine name cannot be empty',

  // Operation failures
  BRIDGE_RENAME_FAILED: 'Failed to rename bridge',
  MACHINE_RENAME_FAILED: 'Failed to rename machine',
  REGION_RENAME_FAILED: 'Failed to rename region',
  BRIDGE_VAULT_UPDATE_FAILED: 'Failed to update vault data for bridge',
  MACHINE_VAULT_UPDATE_FAILED: 'Failed to update vault data for machine',
  REGION_VAULT_UPDATE_FAILED: 'Failed to update vault data for region',

  // Authorization
  USER_VALIDATION_FAILED: 'User validation failed',
  BRIDGE_ACCESS_RESTRICTION: 'You can only assign machines to bridges already used by your team',
  BRIDGE_CLOUD_ONLY_GLOBAL: 'Only Global Bridges can be Cloud Managed',

  // Region errors
  REGION_NOT_FOUND: 'not found in your organization',
  REGION_ALREADY_EXISTS: 'already exists for this organization',
  REGION_CANNOT_DELETE_DEFAULT: 'Cannot delete the default',
  REGION_CANNOT_RENAME_DEFAULT: 'Cannot rename the default',

  // User errors (from db_middleware_auth.sql)
  USER_EMAIL_NOT_FOUND: 'not found in your organization',
  USER_ALREADY_EXISTS: 'already exists',
  USER_CANNOT_DEACTIVATE_SELF: 'cannot deactivate your own account',
  USER_CANNOT_DELETE_LAST_ADMIN: 'Cannot deactivate the last administrator',
  USER_ALREADY_ACTIVATED: 'already activated',

  // ========================================
  // AUTH ERRORS (from db_middleware_auth.sql)
  // ========================================

  // Activation code validation
  ACTIVATION_CODE_INVALID_LENGTH: 'Activation code must be exactly 6 characters',
  ACTIVATION_CODE_NOT_FOUND: 'No activation code found for user',
  ACTIVATION_TOO_MANY_ATTEMPTS: 'Too many failed activation attempts',
  ACTIVATION_CODE_INVALID_ATTEMPTS: 'Invalid activation code. You have',
  ACTIVATION_CODE_MAX_ATTEMPTS: 'Maximum attempts reached',
  ACTIVATION_FAILED: 'Failed to activate user',

  // Login/authentication
  LOGIN_EMAIL_REQUIRED: 'User email is required',
  LOGIN_HASH_INVALID: 'User hash must be exactly 32 bytes',
  LOGIN_REQUEST_NAME_REQUIRED: 'Request name cannot be empty',
  LOGIN_VERIFICATION_REQUIRED: 'Verification data cannot be empty',
  LOGIN_USER_NOT_ACTIVATED: 'not found or not activated',
  LOGIN_INVALID_PASSWORD: 'Invalid password for user',
  LOGIN_ORGANIZATION_MAINTENANCE: 'Organization vault update in progress',

  // Token management
  TOKEN_EXPIRATION_INVALID: 'Token expiration must be between 1 and 720 hours',
  TOKEN_BRIDGE_TARGET_REQUIRED: 'Target (Bridge name) is required',
  TOKEN_PRIVILEGE_INSUFFICIENT:
    'You can only create tokens for groups with equal or fewer privileges',
  TOKEN_ADMIN_ONLY: 'Only administrators can create tokens',
  TOKEN_CHILD_NAME_REQUIRED: 'Child name is required',
  TOKEN_NAME_ALREADY_EXISTS: 'already exists for this user',

  // TFA/Session (extended)
  TFA_CODE_REQUIRED_SESSION: 'TFA code is required to authorize this session',
  TFA_NOT_ENABLED_USER: 'TFA is not enabled for this user account',
  TFA_SESSION_UPDATE_FAILED: 'Failed to update authorization status',
  TFA_SECRET_STORE_FAILED: 'Failed to store TFA secret',
  TFA_SECRET_REMOVE_FAILED: 'Failed to remove TFA secret',
  TFA_DECRYPT_FAILED: 'Unable to decrypt TFA secret',
  TFA_SECRET_VERIFICATION_REQUIRED: 'Secret and verification code are required',
  TFA_INVALID_BASE32: 'Invalid Base32 character detected',

  // User creation
  CREATE_USER_EMAIL_EXISTS: 'already exists',
  CREATE_USER_DEFAULT_PERMISSION_MISSING: 'Default "Users" permission group not found',
  CREATE_USER_INSUFFICIENT_PERMISSION: 'do not have permission to create users',

  // User updates
  UPDATE_EMAIL_INVALID_FORMAT: 'Invalid email format for new user email',
  UPDATE_EMAIL_FAILED: 'Failed to update email for user',
  UPDATE_PASSWORD_FAILED: 'Failed to update password for user',
  UPDATE_PASSWORD_NO_ORGANIZATION: 'No organization association found for user',

  // User deactivation/reactivation
  DEACTIVATE_USER_FAILED: 'Failed to deactivate user',
  REACTIVATE_USER_FAILED: 'Failed to activate user',

  // Registration
  SIGNUP_INVALID_PLAN: 'Subscription plan',

  // Repository errors
  REPOSITORY_NOT_FOUND: 'not found in team',
  REPOSITORY_ALREADY_EXISTS: 'already exists in team',
  REPOSITORY_TAG_EMPTY: 'tag cannot be empty',
  REPOSITORY_FORK_LATEST: 'Fork repositories cannot use',
  REPOSITORY_HAS_FORKS: 'active fork',
  REPOSITORY_LIMIT_EXCEEDED: 'Resource limit exceeded',
  REPOSITORY_INVALID_NETWORK: 'Invalid network mode',
  REPOSITORY_PARENT_NOT_FOUND: 'Parent repository',
  REPOSITORY_NAME_EMPTY: 'name cannot be empty',

  // Storage errors
  STORAGE_NOT_FOUND: 'not found in team',
  STORAGE_ALREADY_EXISTS: 'already exists in team',
  STORAGE_NAME_EMPTY: 'name cannot be empty',

  // Queue errors
  QUEUE_PRIORITY_INVALID: 'Priority must be between 1 and 5',
  QUEUE_NOT_FOUND: 'not found',
  QUEUE_CANNOT_CANCEL: 'cannot be cancelled',
  QUEUE_ALREADY_CANCELLED: 'already cancelled',
  QUEUE_CANNOT_RETRY: 'only retry failed',

  // Permission errors
  PERMISSION_GROUP_NOT_FOUND: 'not found in your organization',
  PERMISSION_GROUP_ALREADY_EXISTS: 'already exists for this organization',
  PERMISSION_GROUP_COMMUNITY_RESTRICTION: 'not available in the Community edition',
  PERMISSION_CANNOT_MODIFY_SYSTEM: 'This is a protected group',
  PERMISSION_GROUP_IN_USE: 'in use by',
  PERMISSION_INVALID_NAME: 'does not exist in the system',
  PERMISSION_ADMIN_ONLY: 'restricted to Administrators',

  // General validation
  REQUEST_VALIDATION_FAILED: 'Request validation failed',
  INVALID_EMAIL_FORMAT: 'Invalid email format',

  // TFA errors (from db_middleware_tfa.sql and db_middleware_auth.sql)
  TFA_ALREADY_ENABLED: 'TFA is already enabled',
  TFA_NOT_ENABLED: 'TFA is not enabled',
  TFA_INVALID_CODE: 'Invalid TFA code',
  TFA_CODE_REQUIRED: 'TFA code is required',
  TFA_VERIFICATION_FAILED: 'Invalid verification code',

  // ========================================
  // ORGANIZATION ERRORS (from db_middleware_organization.sql)
  // ========================================

  // Vault update failures
  VAULT_UPDATE_ORGANIZATION_FAILED: 'Failed to update vault data for organization',
  VAULT_UPDATE_USER_FAILED: 'Failed to update vault data for user',
  VAULT_UPDATE_TEAM_FAILED: 'Failed to update vault data for team',
  VAULT_BULK_UPDATE_FAILED: 'Failed to update vault for credential',
  VAULT_INITIAL_CREATE_FAILED: 'Failed to create initial user vault',

  // Vault validation
  USER_VAULT_EMPTY: 'User vault data cannot be null or empty',

  // Bulk vault conflicts
  VAULT_BULK_NOT_OWNED: 'vault(s) do not belong to this organization',
  VAULT_BULK_VERSION_CONFLICT: 'vault(s) have newer versions than provided',
  VAULT_BULK_BRIDGE_LOCKED: 'Global Bridge with RequestToken set',

  // Team operations
  TEAM_RENAME_FAILED: 'Failed to rename team',
  TEAM_MEMBER_REMOVE_FAILED: 'Failed to remove user',

  // Queue parameter validation
  QUEUE_PARAM_INVALID_CHARS: 'Invalid characters in',
  QUEUE_PRIORITY_MIN_INVALID: 'Minimum priority must be between 1 and 5',
  QUEUE_PRIORITY_MAX_INVALID: 'Maximum priority must be between 1 and 5',
} as const;
