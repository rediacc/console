import { describe, it } from 'vitest';
import { runCli } from '../helpers/cli.js';
import { expectError, nonExistentName } from '../helpers/errors.js';

/**
 * Negative test cases for auth commands.
 *
 * NOTE: Most auth errors are NOT testable because they require:
 * - Interactive login (TFA prompts, password prompts)
 * - Expired tokens (time-based scenarios)
 * - Rate limiting (multiple failed attempts)
 * - Email verification codes
 *
 * The few testable scenarios are included below.
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
      // The backend returns a general error, not a specific "not found" message
      expectError(result, { messageContains: 'error' });
    });
  });
});
