import { Secret, TOTP } from 'otpauth';
import { type CliResult, CliTestRunner } from './CliTestRunner';

/**
 * Generate a valid TOTP code from a Base32 secret.
 * Uses the same parameters as the middleware implementation:
 * - Algorithm: HMAC-SHA1
 * - Period: 30 seconds
 * - Digits: 6
 */
export function generateTOTPCode(base32Secret: string): string {
  const totp = new TOTP({
    secret: Secret.fromBase32(base32Secret),
    algorithm: 'SHA1',
    digits: 6,
    period: 30,
  });
  return totp.generate();
}

/**
 * Wait for a fresh TOTP period before generating a code.
 * This ensures we have enough time for the API call to complete before the code expires.
 * Waits until we're in the first 10 seconds of a 30-second period.
 */
export async function generateFreshTOTPCode(base32Secret: string): Promise<string> {
  const period = 30;
  const safeWindow = 10; // Use first 10 seconds of period

  const now = Math.floor(Date.now() / 1000);
  const secondsIntoCurrentPeriod = now % period;

  if (secondsIntoCurrentPeriod > safeWindow) {
    // Wait until next period starts
    const waitTime = (period - secondsIntoCurrentPeriod) * 1000;
    await new Promise((resolve) => setTimeout(resolve, waitTime));
  }

  return generateTOTPCode(base32Secret);
}

/**
 * Extract TFA secret from CLI enable output.
 * The secret is a 32-character Base32-encoded string.
 */
export function extractSecret(result: CliResult): string | null {
  // Try JSON output first
  if (result.json && typeof result.json === 'object') {
    const json = result.json as Record<string, unknown>;
    if (typeof json.secret === 'string') {
      return json.secret;
    }
  }

  // Fall back to parsing stdout for setup key pattern
  // Matches: "Setup key: ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
  const match = result.stdout.match(/(?:Setup key|secret)[:\s]+([A-Z2-7]{32})/i);
  return match?.[1] ?? null;
}

/**
 * Enable TFA and return the secret.
 */
export async function enableTFA(
  runner: CliTestRunner
): Promise<{ secret: string | null; success: boolean }> {
  const result = await runner.run(['auth', 'tfa', 'enable']);
  if (!result.success) {
    return { secret: null, success: false };
  }
  const secret = extractSecret(result);
  return { secret, success: true };
}

/**
 * Disable TFA using a valid TOTP code generated from the secret.
 * Uses generateFreshTOTPCode to ensure we have time for the API call.
 */
export async function disableTFA(runner: CliTestRunner, secret: string): Promise<boolean> {
  const code = await generateFreshTOTPCode(secret);
  const result = await runner.run(['auth', 'tfa', 'disable', '--code', code, '--yes']);
  return result.success;
}

/**
 * Check current TFA status.
 */
export async function getTFAStatus(
  runner: CliTestRunner
): Promise<{ enabled: boolean; success: boolean }> {
  const result = await runner.run(['auth', 'tfa', 'status']);
  if (!result.success) {
    return { enabled: false, success: false };
  }
  // Check output for enabled/disabled status
  const enabled = /enabled/i.test(result.stdout) && !/not enabled/i.test(result.stdout);
  return { enabled, success: true };
}
