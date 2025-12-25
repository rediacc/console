import { expect } from 'vitest';
import { getErrorMessage, type CliResult } from './cli.js';

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
  // Team errors (from db_middleware_company.sql)
  TEAM_NOT_FOUND: 'not found in your company',
  TEAM_ALREADY_EXISTS: 'already exists in your company',
  TEAM_NOT_MEMBER: 'not a member of team',
  TEAM_CANNOT_DELETE_DEFAULT: 'Cannot delete the default',
  TEAM_CANNOT_DELETE_LAST: 'Cannot remove the last team',
  TEAM_CANNOT_RENAME_DEFAULT: 'Cannot rename the default',
  TEAM_NAME_EMPTY: 'cannot be empty',
  TEAM_VAULT_EMPTY: 'vault data cannot be null or empty',

  // Team membership errors
  USER_NOT_FOUND_IN_COMPANY: 'not found, not activated, or not in your company',
  USER_ALREADY_MEMBER: 'already a member of team',
  CANNOT_REMOVE_SELF: 'cannot remove yourself',
  BRIDGE_USER_CANNOT_JOIN: 'Bridge users cannot be added to teams',

  // Machine errors (from db_middleware_infrastructure.sql)
  MACHINE_NOT_FOUND: 'not found in team',
  MACHINE_ALREADY_EXISTS: 'already exists in your company',
  MACHINE_BRIDGE_MISMATCH: 'not assigned to bridge',

  // Bridge errors
  BRIDGE_NOT_FOUND: 'not found in region',
  BRIDGE_ALREADY_EXISTS: 'already exists in region',
  BRIDGE_CANNOT_DELETE_DEFAULT: 'Cannot delete the default',

  // Region errors
  REGION_NOT_FOUND: 'not found in your company',
  REGION_ALREADY_EXISTS: 'already exists for this company',
  REGION_CANNOT_DELETE_DEFAULT: 'Cannot delete the default',
  REGION_CANNOT_RENAME_DEFAULT: 'Cannot rename the default',

  // User errors (from db_middleware_auth.sql)
  USER_EMAIL_NOT_FOUND: 'not found in your company',
  USER_ALREADY_EXISTS: 'already exists',
  USER_CANNOT_DEACTIVATE_SELF: 'cannot deactivate your own account',
  USER_CANNOT_DELETE_LAST_ADMIN: 'Cannot deactivate the last administrator',
  USER_ALREADY_ACTIVATED: 'already activated',

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
  PERMISSION_GROUP_NOT_FOUND: 'not found in your company',
  PERMISSION_GROUP_ALREADY_EXISTS: 'already exists for this company',
  PERMISSION_GROUP_COMMUNITY_RESTRICTION: 'not available in the Community edition',
  PERMISSION_CANNOT_MODIFY_SYSTEM: 'This is a protected group',
  PERMISSION_GROUP_IN_USE: 'in use by',
  PERMISSION_INVALID_NAME: 'does not exist in the system',
  PERMISSION_ADMIN_ONLY: 'restricted to Administrators',

  // General validation
  REQUEST_VALIDATION_FAILED: 'Request validation failed',
  INVALID_EMAIL_FORMAT: 'Invalid email format',
} as const;
