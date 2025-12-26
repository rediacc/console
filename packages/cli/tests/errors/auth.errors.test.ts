import { describe, it } from 'vitest';
import { runCli } from '../helpers/cli.js';
import { ErrorPatterns, expectError, nonExistentName } from '../helpers/errors.js';

/**
 * Negative test cases for auth commands.
 *
 * NOTE: Most auth errors are NOT testable via CLI because they require:
 * - Interactive login (TFA prompts, password prompts)
 * - Expired tokens (time-based scenarios)
 * - Rate limiting (multiple failed attempts)
 * - Email verification codes
 * - Activation flows with 6-character codes
 *
 * ErrorPatterns coverage for auth (documented for reference):
 *
 * TESTABLE via CLI:
 * - TOKEN_NAME_ALREADY_EXISTS - requires creating duplicate child tokens
 *
 * NOT TESTABLE (require interactive flows or special conditions):
 * - ACTIVATION_CODE_INVALID_LENGTH - requires activation flow
 * - ACTIVATION_CODE_NOT_FOUND - requires activation flow
 * - ACTIVATION_TOO_MANY_ATTEMPTS - requires rate limiting
 * - ACTIVATION_CODE_INVALID_ATTEMPTS - requires activation flow
 * - ACTIVATION_CODE_MAX_ATTEMPTS - requires rate limiting
 * - ACTIVATION_FAILED - internal server error
 * - LOGIN_EMAIL_REQUIRED - requires login flow
 * - LOGIN_HASH_INVALID - requires login flow
 * - LOGIN_REQUEST_NAME_REQUIRED - requires login flow
 * - LOGIN_VERIFICATION_REQUIRED - requires login flow
 * - LOGIN_USER_NOT_ACTIVATED - requires login flow
 * - LOGIN_INVALID_PASSWORD - requires login flow
 * - LOGIN_COMPANY_MAINTENANCE - requires vault update in progress
 * - TOKEN_EXPIRATION_INVALID - tested indirectly via token create
 * - TOKEN_BRIDGE_TARGET_REQUIRED - requires bridge token creation
 * - TOKEN_PRIVILEGE_INSUFFICIENT - requires permission group mismatch
 * - TOKEN_ADMIN_ONLY - requires non-admin user
 * - TOKEN_CHILD_NAME_REQUIRED - requires child token creation
 * - TFA_CODE_REQUIRED_SESSION - requires active TFA
 * - TFA_NOT_ENABLED_USER - requires TFA disable attempt
 * - TFA_SESSION_UPDATE_FAILED - internal server error
 * - TFA_SECRET_STORE_FAILED - internal server error
 * - TFA_SECRET_REMOVE_FAILED - internal server error
 * - TFA_DECRYPT_FAILED - requires corrupted TFA data
 * - TFA_SECRET_VERIFICATION_REQUIRED - requires TFA setup flow
 * - TFA_INVALID_BASE32 - requires malformed TFA secret
 * - CREATE_USER_EMAIL_EXISTS - tested in user.errors.test.ts
 * - CREATE_USER_DEFAULT_PERMISSION_MISSING - requires missing permission group
 * - CREATE_USER_INSUFFICIENT_PERMISSION - requires non-admin user
 * - UPDATE_EMAIL_INVALID_FORMAT - tested in user.errors.test.ts
 * - UPDATE_EMAIL_FAILED - internal server error
 * - UPDATE_PASSWORD_FAILED - internal server error
 * - UPDATE_PASSWORD_NO_COMPANY - requires orphaned user
 * - DEACTIVATE_USER_FAILED - internal server error
 * - REACTIVATE_USER_FAILED - internal server error
 * - SIGNUP_INVALID_PLAN - requires signup with invalid plan
 *
 * User-related errors (email updates, etc.) are tested in user.errors.test.ts.
 */
describe('auth error scenarios', () => {
  // ============================================
  // Token Revoke Errors
  // ============================================
  describe('Token revoke errors', () => {
    it('should fail when revoking non-existent token', async () => {
      const fakeRequestId = nonExistentName('request');
      const result = await runCli(['auth', 'token', 'revoke', fakeRequestId]);

      // API should return an error for non-existent request ID
      expectError(result, { messageContains: ErrorPatterns.QUEUE_NOT_FOUND });
    });
  });

  // ============================================
  // Token Create Errors
  // ============================================
  describe('Token create errors', () => {
    it('should fail with invalid token expiration hours', async () => {
      // Token expiration must be between 1 and 720 hours
      const result = await runCli(['auth', 'token', 'create', '--expiration', '0']);

      // This may be caught by CLI validation or backend
      expectError(result, { messageContains: 'expiration' });
    });

    it('should fail with excessive token expiration hours', async () => {
      // Token expiration must be between 1 and 720 hours (30 days max)
      const result = await runCli(['auth', 'token', 'create', '--expiration', '1000']);

      expectError(result, { messageContains: ErrorPatterns.TOKEN_EXPIRATION_INVALID });
    });
  });
});
